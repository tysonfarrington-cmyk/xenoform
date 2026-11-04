/* Xenoform Perform, the control view (docs/UI_REVIEW.md 6.5). vj.html holds the engine (renderer, director, recorder)
   and the sound; this draws the controls around it and links the output window (/vj?out=1) over a BroadcastChannel
   ("xeno-rig"): the control view sends state (the scenes, the song's analysis, the look, the knobs, the held pad, REC),
   the output renders and records and reports back its size, fps and REC state. The song plays here, so the output reads
   this window's clock and sound directly (window.opener.XPA). With no output window this window renders, as before.
   Nothing here is drawn into the canvas: REC, the HUD, toasts and the cursor can never be in a take. */
(function () {
  "use strict";
  if (document.documentElement.classList.contains("out")) { window.XP = { monitor() {} }; return; }
  const $ = (id) => document.getElementById(id);
  const Q = new URLSearchParams(location.search);
  const S = VJ.S;
  const PARAMS = ["fx", "every", "inten", "mir", "stb", "kal", "master", "black", "glow", "speed", "chaos", "pics", "hud"];
  const LOOKS = { strobe: "Strobe", mirror: "Mirror", freeze: "Freeze", invert: "Invert", kaleido: "Kaleido" };
  const ROLE_NAMES = { intro: "intro", calm: "calm", sustain: "sustain", build: "build", release: "release", drop: "drop", drop_late: "late drop", outro: "outro" };
  const C = {
    out: "", last: null, lastAt: 0, win: null, wantFull: false, openedAt: 0, stream: null,
    song: null, songFor: 0, token: 0, title: "", job: null, spec: { cut: [], lib: null, files: [], stills: [] },
    pads: [], holds: [], held: null, cue: null, recSeen: "", lastTake: null, toastT: 0, solo: false, knobs: {},
  };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clock = (t) => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = Math.floor(t % 60); return m + ":" + String(s).padStart(2, "0"); };
  const now = () => performance.now();

  // ---------------------------------------------------------------- the link to the output window
  const bc = new BroadcastChannel("xeno-rig");
  const linked = () => !!C.out;
  const params = () => { const o = {}; PARAMS.forEach((k) => { o[k] = S[k]; }); o.gain = Object.assign({}, S.gain); return o; };
  const snapshot = () => ({ set: params(), song: C.song, stems: XC.stemsUrl() || null, scenes: C.spec, hold: S.hold });
  // every command reaches this window's engine (asleep while an output is linked, so it wakes up current) and the output's;
  // REC only reaches the engine that is drawing
  function send(op, a, o) {
    o = o || {};
    const active = op === "rec";
    if (!active || !linked()) VJ.cmd(op, a);
    if (linked() && o.remote !== false) bc.postMessage({ t: "cmd", to: C.out, op, a: a || {} });
  }
  function set(o) { send("set", o); paintLook(); }
  function link(m) {
    if (C.out === m.id) return;
    if (C.out && C.lastAt && now() - C.lastAt < 1500) return;  // one output at a time: the live one keeps the link
    C.out = m.id; C.last = m.r || null; C.lastAt = now();
    bc.postMessage({ t: "cmd", to: m.id, op: "sync", a: snapshot() });
    VJ.cmd("sleep");
    $("screen").classList.add("linked");
    if (C.wantFull && C.win && now() - C.openedAt < 4800) {  // the click that opened it also makes it fullscreen (capability delegation)
      try { C.win.postMessage({ t: "fullscreen" }, { targetOrigin: location.origin, delegate: "fullscreen" }); } catch (e) { /* older Chrome */ }
    }
    const placed = C.wantFull;
    C.wantFull = false;
    paintOut();
    toast(placed ? "The output window is on your second screen. Fullscreen output (F) fills it; this view is the monitor."
      : "The output window is live. This view is the monitor.");
  }
  function unlink(why) {
    if (!C.out) return;
    const last = C.last;
    C.out = ""; C.last = null; C.stream = null;
    const mon = $("mon"); mon.srcObject = null; mon.hidden = true;
    $("screen").classList.remove("linked");
    VJ.cmd("wake");
    if (last && last.rec && last.rec.on && last.rec.id) {  // the take ran in the window that went: keep what reached the desk
      fetch(`/api/perform/takes/${last.rec.id}/finish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then((r) => r.json()).then((t) => { C.lastTake = t; paintRec(); }).catch(() => {});
      toast("The output window closed during a take: the desk keeps what reached it, as an mp4 in My videos.");
    } else toast(why === "lost" ? "The output window stopped answering: the picture is back in this window." : "The output window closed: the picture is back in this window.");
    paintOut();
  }
  bc.onmessage = (e) => {
    const m = e.data || {};
    if (m.t === "hello-out" || (m.t === "report" && !C.out)) link(m);
    if (m.id !== C.out) return;
    if (m.t === "report") { C.last = m.r; C.lastAt = now(); }
    else if (m.t === "toast") toast(m.text);
    else if (m.t === "bye-out") unlink("closed");
  };
  bc.postMessage({ t: "hello-ctl" });
  addEventListener("pagehide", () => bc.postMessage({ t: "bye-ctl" }));
  // the output's canvas, live, as this view's monitor (the output hands its stream over when it links)
  function monitor(stream, id) {
    if (C.out && id && id !== C.out) return;
    C.stream = stream;
    const mon = $("mon");
    if (mon.srcObject !== stream) mon.srcObject = stream;
    mon.hidden = false;
    mon.play().catch(() => {});
  }
  // the report the controls read: the drawing engine's (this window's, or the output's)
  const R = () => (linked() && C.last ? C.last : VJ.report());
  const recording = () => !!(R().rec && R().rec.on);

  // ---------------------------------------------------------------- the output window
  function passThrough() {
    const keep = ["w", "h", "fps", "sync", "seed", "classic", "expert", "vbr"];
    const p = new URLSearchParams();
    keep.forEach((k) => { if (Q.get(k) != null) p.set(k, Q.get(k)); });
    const s = p.toString();
    return s ? "&" + s : "";
  }
  async function openOutput() {
    if (C.win && !C.win.closed) { try { C.win.focus(); } catch (e) {} fullscreen(); return; }
    let feat = "popup,width=1280,height=720", other = null, why = "", prompted = false;
    if ("getScreenDetails" in window) {  // Chromium's Window Management API: place it on the other screen
      try { prompted = (await navigator.permissions.query({ name: "window-management" })).state === "prompt"; } catch (e) { /* an older name */ }
      try {
        const sd = await window.getScreenDetails();
        other = sd.screens.find((s) => s !== sd.currentScreen) || null;
        if (other) feat = `popup,left=${other.availLeft},top=${other.availTop},width=${other.availWidth},height=${other.availHeight}`;
        else why = "one";
      } catch (e) { why = "denied"; }
    }
    const w = window.open("/vj?out=1" + passThrough(), "xeno-out", feat);
    if (!w) {  // the first time, the browser's question about your screens can use up the click that opens the window
      toast(prompted ? "Thanks. Press Open output window once more to open it on your second screen."
        : "The browser blocked the window. Allow pop-ups for this desk, then press Open output window again.");
      return;
    }
    C.win = w; C.wantFull = !!other; C.openedAt = now();
    $("outnote").hidden = true;
    if (!other) toast(why === "one" ? "One screen found: drag the output window where you want it, then double-click it for fullscreen."
      : "Drag the output window onto your second screen, then double-click it for fullscreen.");
  }
  function fullscreen() {
    if (linked()) {
      if (C.win && !C.win.closed) { try { C.win.postMessage({ t: "fullscreen" }, { targetOrigin: location.origin, delegate: "fullscreen" }); C.win.focus(); } catch (e) {} }
      else toast("Double-click the output window to make it fullscreen.");
      return;
    }
    const st = $("stage");
    if (document.fullscreenElement) document.exitFullscreen(); else st.requestFullscreen().catch(() => {});
  }
  function paintOut() {
    const r = linked() && C.last;
    $("out-line").textContent = r ? `Output: its own window${r.full ? ", fullscreen" : ""} · ${r.w}×${r.h} · ${r.fps || "-"} fps` : "Output: this window";
    $("outb").textContent = linked() ? "Output window is live" : "Open output window";
    $("outb").classList.toggle("on", linked());
    $("fs").textContent = linked() ? "Fullscreen output" : "Fullscreen";
  }

  // ---------------------------------------------------------------- the song: transport, cue
  const track = () => XC.track;
  function togglePlay() {
    const t = track();
    if (!t) { toast("Load a track first."); return; }
    if (XC.mic) { XC.micOff(); paintSource(); }
    XC.ensureAC().resume();
    if (t.paused) t.play(); else t.pause();
    C.cue = null;
    paintTransport();
  }
  function seek(t) {
    const tr = track();
    if (!tr) return;
    tr.currentTime = Math.max(0, Math.min(tr.duration - 0.05, t));
    C.cue = null;
  }
  // a cue lands on the grid when the song is playing: the next bar (the next beat when the switch is on every beat)
  function cue(t, label) {
    const tr = track();
    if (!tr) return;
    if (tr.paused) { seek(t); toast("Cued " + label); return; }
    const grid = (S.every === 1 ? C.song && C.song.beats : (C.song && (C.song.bars && C.song.bars.length ? C.song.bars : C.song.beats))) || [];
    const pos = tr.currentTime, at = grid.find((b) => b > pos + 0.03);
    if (at == null) { seek(t); return; }
    C.cue = { at, to: t, label };
  }
  function drops() {
    const P = (C.song && C.song.passages) || [];
    const d = P.filter((p) => p.drop_run != null || /^drop/.test(p.role));
    return d.length ? d : C.song && C.song.drop != null ? [{ role: "drop", start: C.song.drop, end: C.song.drop }] : [];
  }
  function label(p) {
    if (!p) return "";
    if (p.drop_run != null || /^drop/.test(p.role)) { const all = drops(); const n = all.indexOf(p) + 1; return "drop" + (all.length > 1 && n > 0 ? " " + n : ""); }
    return ROLE_NAMES[p.role] || p.role || "song";
  }
  function cueDrop() {
    const tr = track(), all = drops();
    if (!tr || !all.length) { toast(tr ? "This song's analysis has no drop to cue." : "Load a track first."); return; }
    const pos = tr.currentTime;
    const p = all.find((d) => d.start > pos + 0.25) || all[0];
    cue(p.start, label(p));
  }
  function paintTransport() {
    const t = track();
    const play = $("playb");
    play.disabled = !t;
    play.textContent = t && !t.paused ? "Pause" : "Play";
    $("cueb").disabled = !t || !drops().length;
    $("tapb").hidden = !XC.mic;
    $("clock").textContent = t ? `${clock(t.currentTime)} / ${clock(t.duration)}` : XC.mic ? "live input" : "0:00 / 0:00";
    document.querySelectorAll("#every [data-every]").forEach((b) => b.classList.toggle("on", +b.dataset.every === S.every));
  }

  // ---------------------------------------------------------------- the strip
  const strip = $("strip");
  const ROLE_COLOUR = {};  // read from the stylesheet once: the strip redraws every frame
  const roleColour = (role) => {
    const key = String(role || "sustain").replace("_", "-");
    if (!(key in ROLE_COLOUR)) {
      const css = getComputedStyle(document.documentElement);
      ROLE_COLOUR[key] = css.getPropertyValue("--pf-role-" + key).trim() || css.getPropertyValue("--pf-role-sustain").trim() || "#3a3a48";
    }
    return ROLE_COLOUR[key];
  };
  let FONT = "";
  const font = (w, px) => (FONT || (FONT = getComputedStyle(document.body).fontFamily), `${w} ${px}px ${FONT}`);
  const LANE = { sec: [4, 34], beat: [38, 52], shot: [56, 86], pad: [90, 104] };
  function stripLayout() {
    const dpr = devicePixelRatio || 1, w = Math.max(200, strip.clientWidth), h = strip.clientHeight || 132;
    if (strip.width !== Math.round(w * dpr) || strip.height !== Math.round(h * dpr)) { strip.width = Math.round(w * dpr); strip.height = Math.round(h * dpr); }
    return { dpr, w, h };
  }
  function drawStrip() {
    const { dpr, w, h } = stripLayout();
    const g = strip.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const tr = track(), song = C.song, dur = (tr && tr.duration) || (song && song.duration) || 0;
    g.font = font(600, 11);
    g.textBaseline = "middle";
    if (!dur) { g.fillStyle = "rgba(255,255,255,.05)"; g.fillRect(0, LANE.sec[0], w, LANE.sec[1] - LANE.sec[0]); return; }
    const X = (t) => (t / dur) * w;
    // sections, coloured by role; drop runs by their heat; the main one outlined
    const P = (song && song.passages) || [];
    P.forEach((p) => {
      const x0 = X(p.start), x1 = X(p.end);
      g.globalAlpha = p.drop_run != null ? 0.55 + 0.45 * (p.heat == null ? 1 : p.heat) : 0.85;
      g.fillStyle = roleColour(p.role);
      g.fillRect(x0, LANE.sec[0], Math.max(1, x1 - x0 - 1), LANE.sec[1] - LANE.sec[0]);
      g.globalAlpha = 1;
      if (p.main) { g.strokeStyle = "rgba(255,255,255,.8)"; g.lineWidth = 1.5; g.strokeRect(x0 + 0.75, LANE.sec[0] + 0.75, Math.max(1, x1 - x0 - 2.5), LANE.sec[1] - LANE.sec[0] - 1.5); }
      const name = label(p).toUpperCase();
      if (x1 - x0 > g.measureText(name).width + 10) { g.fillStyle = "#fff"; g.fillText(name, x0 + 6, (LANE.sec[0] + LANE.sec[1]) / 2); }
    });
    if (song && song.wave && song.wave.length) {  // the waveform, faint, over the sections
      g.fillStyle = "rgba(255,255,255,.16)";
      const n = song.wave.length, mid = (LANE.sec[0] + LANE.sec[1]) / 2, amp = (LANE.sec[1] - LANE.sec[0]) / 2 - 2;
      for (let i = 0; i < n; i++) { const v = Math.abs(+song.wave[i] || 0) * amp; g.fillRect((i / n) * w, mid - v, Math.max(1, w / n), v * 2); }
    }
    // beats and bars
    const beats = (song && song.beats) || [], bars = new Set(((song && song.bars) || []).map((b) => b.toFixed(3)));
    g.fillStyle = "rgba(255,255,255,.07)"; g.fillRect(0, LANE.beat[0], w, LANE.beat[1] - LANE.beat[0]);
    beats.forEach((b) => {
      const bar = bars.has(b.toFixed(3));
      g.fillStyle = bar ? "rgba(255,255,255,.75)" : "rgba(255,255,255,.28)";
      const x = X(b), top = bar ? LANE.beat[0] : LANE.beat[0] + 6;
      g.fillRect(Math.round(x), top, 1, LANE.beat[1] - top);
    });
    // the drops
    drops().forEach((p) => { const x = X(p.start); g.fillStyle = "#fff"; g.beginPath(); g.moveTo(x - 5, 0); g.lineTo(x + 5, 0); g.lineTo(x, 7); g.fill(); });
    // the cut's shots
    const shots = (song && song.shots) || [];
    if (shots.length) {
      shots.forEach((s, i) => {
        if (s.end - s.start <= 0) return;
        const x0 = X(s.start), x1 = X(s.end), on = R().shot === i && S.pics === "cut";
        g.fillStyle = on ? "rgba(124,108,255,.55)" : i % 2 ? "rgba(255,255,255,.10)" : "rgba(255,255,255,.16)";
        g.fillRect(x0, LANE.shot[0], Math.max(1, x1 - x0 - 1), LANE.shot[1] - LANE.shot[0]);
        const name = s.to || "";
        if (name && x1 - x0 > 40) {
          g.save(); g.beginPath(); g.rect(x0 + 3, LANE.shot[0], x1 - x0 - 6, LANE.shot[1] - LANE.shot[0]); g.clip();
          g.fillStyle = "rgba(255,255,255,.85)"; g.font = font(500, 10.5); g.fillText(name, x0 + 5, (LANE.shot[0] + LANE.shot[1]) / 2); g.restore();
        }
      });
    }
    // the pads' holds, as blocks on their lane
    g.fillStyle = "rgba(255,255,255,.05)"; g.fillRect(0, LANE.pad[0], w, LANE.pad[1] - LANE.pad[0]);
    const pos = tr ? tr.currentTime : 0;
    C.holds.forEach((hb) => {
      const x0 = X(hb.start), x1 = X(hb.end == null ? pos : hb.end);
      g.fillStyle = "rgba(242,177,74,.85)"; g.fillRect(x0, LANE.pad[0], Math.max(2, x1 - x0), LANE.pad[1] - LANE.pad[0]);
      if (x1 - x0 > 18) { g.fillStyle = "#111"; g.font = font(700, 10); g.fillText(String(hb.pad), x0 + 4, (LANE.pad[0] + LANE.pad[1]) / 2); }
    });
    // a cue waiting for its bar
    if (C.cue) { const x = X(C.cue.to); g.strokeStyle = "rgba(255,255,255,.9)"; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke(); g.setLineDash([]); }
    // the playhead
    const x = X(pos);
    g.fillStyle = "#ff6464"; g.fillRect(Math.round(x) - 1, 0, 2, h - 14);
    g.fillStyle = "rgba(236,236,241,.9)"; g.font = font(500, 11); g.textBaseline = "alphabetic";
    const lab = clock(pos), lw = g.measureText(lab).width;
    g.fillText(lab, Math.min(w - lw - 2, Math.max(2, x - lw / 2)), h - 2);
  }
  strip.addEventListener("click", (e) => {
    const tr = track(), song = C.song;
    if (!tr) return;
    const rect = strip.getBoundingClientRect(), t = ((e.clientX - rect.left) / rect.width) * tr.duration, y = e.clientY - rect.top;
    if (y <= LANE.sec[1] + 2 && song && song.passages && song.passages.length) {  // a section: cue it, on the grid
      const p = song.passages.find((q) => t >= q.start && t < q.end);
      if (p) { cue(p.start, label(p)); return; }
    }
    const beats = (song && song.beats) || [];  // elsewhere: jump there, to the nearest beat
    const near = beats.length ? beats.reduce((a, b) => (Math.abs(b - t) < Math.abs(a - t) ? b : a), beats[0]) : t;
    seek(Math.abs(near - t) < 0.4 ? near : t);
  });
  strip.addEventListener("keydown", (e) => {
    const tr = track();
    if (!tr || !/^Arrow(Left|Right)$/.test(e.key)) return;
    e.preventDefault(); e.stopPropagation();
    const bars = (C.song && C.song.bars && C.song.bars.length ? C.song.bars : (C.song && C.song.beats) || []);
    const pos = tr.currentTime;
    const to = e.key === "ArrowRight" ? bars.find((b) => b > pos + 0.05) : [...bars].reverse().find((b) => b < pos - 0.3);
    if (to != null) seek(to);
  });

  // ---------------------------------------------------------------- now / next
  function passageAt(t) { return ((C.song && C.song.passages) || []).find((p) => t >= p.start && t < p.end) || null; }
  function beatsBetween(a, b) { return ((C.song && C.song.beats) || []).filter((x) => x > a + 0.02 && x <= b + 0.02).length; }
  function paintNow() {
    const tr = track(), r = R(), song = C.song;
    let nowL = "Nothing playing", nextL = "-";
    if (XC.mic) { nowL = "Mic / line-in · " + (r.scene || "-"); nextL = "beats from the input" + (S.bpm ? ` · ${S.bpm} BPM` : ""); }
    else if (tr) {
      const pos = tr.currentTime, p = passageAt(pos);
      const shot = song && song.shots && r.shot >= 0 && S.pics === "cut" && S.every === 0 ? song.shots[r.shot] : null;
      nowL = [p ? label(p).toUpperCase() : "", shot ? `shot ${r.shot + 1} · ${shot.to || ""}` : r.scene || ""].filter(Boolean).join(" · ") || clock(pos);
      const P = (song && song.passages) || [];
      const nx = P.find((q) => q.start > pos + 0.02);
      if (nx) {
        const n = beatsBetween(pos, nx.start), isDrop = nx.drop_run != null || /^drop/.test(nx.role);
        nextL = `${label(nx)} · in ${n} beat${n === 1 ? "" : "s"}`;
        if (!isDrop) { const d = drops().find((q) => q.start > pos + 0.02); if (d) { const k = beatsBetween(pos, d.start); nextL += ` · next ${label(d)} in ${k} beats`; } }
      } else nextL = song && song.passages && song.passages.length ? "the end of the song" : "beats only: the desk has not sent this song's sections";
      if (C.cue) nextL = `cued: ${C.cue.label}, on the next ${S.every === 1 ? "beat" : "bar"}`;
    }
    $("now-l").textContent = nowL;
    $("next-l").textContent = nextL;
    const top = XenoMidi.holds.top(), pad = top ? C.pads[top - 1] : null;
    $("held-l").textContent = pad ? `pad ${top} · ${pad.label}: let go and it snaps back to the song${tr ? " at " + clock(tr.currentTime) : ""}` : "Hold a pad to show it; let go and the song carries on.";
    $("held-l").parentElement.classList.toggle("is-held", !!pad);
    const bar = r.bar;
    document.querySelectorAll("#nn-bars i").forEach((el, i) => el.classList.toggle("on", i === bar));
    const src = XC.mic ? "from the input" : !song ? "" : song.src === "cut" ? "the cut's beats" : song.src === "desk" ? "beats from the desk" : "beats from the browser";
    $("nn-bpm").textContent = [song && song.tempo ? Math.round(song.tempo) + " BPM" : S.bpm ? S.bpm + " BPM" : "", src].filter(Boolean).join(" · ");
  }

  // ---------------------------------------------------------------- pads
  const padKey = () => "xeno-pads:" + (C.job ? "job:" + C.job.id : "lib");
  function defaultPads() {
    const out = [], seen = new Set();
    const scenes = S.scenes.filter((s) => !s.bad && (C.job ? s.set === "cut" : s.set === "lib" || s.set === "file"));
    for (const s of scenes) { const n = s.name; if (seen.has(n)) continue; seen.add(n); out.push({ kind: "scene", key: s.key, label: n }); if (out.length >= 5) break; }
    for (const look of ["strobe", "mirror", "freeze", "invert", "kaleido"]) { if (out.length >= 8) break; if (look === "kaleido" && !EXPERT) continue; out.push({ kind: "look", look, label: LOOKS[look] }); }
    while (out.length < 8) out.push({ kind: "look", look: "strobe", label: "Strobe" });
    return out;
  }
  function loadPads() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(padKey()) || "null"); } catch (e) { saved = null; }
    C.pads = Array.isArray(saved) && saved.length === 8 ? saved : defaultPads();
    const stills = C.pads.filter((p) => p.kind === "scene" && /^still:/.test(p.key));
    if (stills.length) addStills(stills.map((p) => ({ url: p.key.slice(6), name: p.label, key: p.key })));
    paintPads();
  }
  function savePads() { try { localStorage.setItem(padKey(), JSON.stringify(C.pads)); } catch (e) {} }
  function paintPads() {
    $("pads").innerHTML = C.pads.map((p, i) => `<button type="button" class="pf-pad${p.kind === "look" ? " is-look" : ""}" data-pad="${i + 1}" data-midi="pad:${i + 1}" title="Hold to show (Shift+${i + 1}); drop a scene or a look here to change it">
      <b>${i + 1}</b><span>${esc(p.label)}</span><small>${p.kind === "look" ? "look" : "scene"}</small></button>`).join("");
    paintHeld();
  }
  // a hold changes classes in place: the button under the finger stays the same element, so its release is its own
  function paintHeld() {
    const top = XenoMidi.holds.top(), stack = XenoMidi.holds.stack || [];
    document.querySelectorAll("#pads [data-pad]").forEach((b) => {
      const n = +b.dataset.pad;
      b.classList.toggle("is-held", top === n);
      b.classList.toggle("is-under", top !== n && stack.includes(n));
      b.setAttribute("aria-pressed", top === n ? "true" : "false");
    });
  }
  function press(n) { if (C.pads[n - 1]) XenoMidi.holds.press(n); }
  function release(n) { XenoMidi.holds.release(n); }
  XenoMidi.holds.on((top) => {
    const tr = track(), pos = tr ? tr.currentTime : 0;
    const open = C.holds.find((h) => h.end == null);
    if (open && open.pad !== top) open.end = pos;
    if (top && (!open || open.pad !== top)) C.holds.push({ pad: top, start: pos, end: null });
    if (C.holds.length > 400) C.holds.splice(0, C.holds.length - 400);
    const h = top ? C.pads[top - 1] : null;
    send("hold", { h: h ? Object.assign({}, h) : null });
    paintHeld();
  });
  const padsEl = $("pads");
  padsEl.addEventListener("pointerdown", (e) => {
    const b = e.target.closest("[data-pad]");
    if (!b || XenoMidi.learnMode || e.button > 0) return;
    e.preventDefault();
    b.setPointerCapture(e.pointerId);
    press(+b.dataset.pad);
  });
  const up = (e) => { const b = e.target.closest && e.target.closest("[data-pad]"); if (b) release(+b.dataset.pad); };
  padsEl.addEventListener("pointerup", up);
  padsEl.addEventListener("pointercancel", up);
  padsEl.addEventListener("lostpointercapture", up);
  padsEl.addEventListener("keydown", (e) => { const b = e.target.closest("[data-pad]"); if (b && (e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); e.stopPropagation(); press(+b.dataset.pad); } });
  padsEl.addEventListener("keyup", (e) => { const b = e.target.closest("[data-pad]"); if (b && (e.key === " " || e.key === "Enter")) { e.preventDefault(); release(+b.dataset.pad); } });
  padsEl.addEventListener("dragover", (e) => { const b = e.target.closest("[data-pad]"); if (b && e.dataTransfer.types.includes("application/x-xeno-pad")) { e.preventDefault(); b.classList.add("is-drop"); } });
  padsEl.addEventListener("dragleave", (e) => { const b = e.target.closest("[data-pad]"); if (b) b.classList.remove("is-drop"); });
  padsEl.addEventListener("drop", (e) => {
    const b = e.target.closest("[data-pad]");
    if (!b) return;
    e.preventDefault();
    let d = null;
    try { d = JSON.parse(e.dataTransfer.getData("application/x-xeno-pad")); } catch (err) { d = null; }
    if (!d) return;
    const n = +b.dataset.pad;
    if (d.kind === "still") { addStills([{ url: d.url, name: d.label, key: "still:" + d.url }]); C.pads[n - 1] = { kind: "scene", key: "still:" + d.url, label: d.label }; }
    else if (d.kind === "look") C.pads[n - 1] = { kind: "look", look: d.look, label: LOOKS[d.look] || d.look };
    else C.pads[n - 1] = { kind: "scene", key: d.key, label: d.label };
    savePads(); paintPads();
    toast(`Pad ${n} is now ${C.pads[n - 1].label}.`);
  });
  function paintBank() {
    const scenes = [];
    S.scenes.forEach((s) => { if (!s.bad && s.set !== "still") scenes.push({ kind: "scene", key: s.key, label: s.name, set: s.set }); });
    ((C.job && C.job.stills) || []).forEach((st) => scenes.push({ kind: "still", url: st.url, label: st.noun || "still", set: "still" }));
    $("bank-scenes").innerHTML = scenes.slice(0, 80).map((s) => `<button type="button" class="chip pf-drag${s.set === "cut" ? " is-cut" : s.set === "still" ? " is-still" : ""}" draggable="true" data-drag="${esc(JSON.stringify(s))}" title="${s.set === "cut" ? "a clip of this cut" : s.set === "still" ? "a still of this cut" : "a library loop"}">${esc(s.label)}</button>`).join("") || `<span class="note">No scenes yet.</span>`;
    $("bank-looks").innerHTML = Object.keys(LOOKS).filter((k) => k !== "kaleido" || EXPERT).map((k) => `<button type="button" class="chip pf-drag" draggable="true" data-drag="${esc(JSON.stringify({ kind: "look", look: k, label: LOOKS[k] }))}">${LOOKS[k]}</button>`).join("");
  }
  $("bank").addEventListener("dragstart", (e) => { const c = e.target.closest("[data-drag]"); if (!c) return; e.dataTransfer.setData("application/x-xeno-pad", c.dataset.drag); e.dataTransfer.effectAllowed = "copy"; });
  $("bank").addEventListener("toggle", () => { if ($("bank").open) paintBank(); });
  $("pads-reset").onclick = () => { C.pads = defaultPads(); savePads(); paintPads(); toast("The pads are back to the cut's objects and the looks."); };
  function addStills(list) {
    const have = new Set(C.spec.stills.map((s) => s.key));
    const add = list.filter((s) => !have.has(s.key));
    if (!add.length) return;
    C.spec.stills = C.spec.stills.concat(add);
    send("scenes", C.spec);
  }
  function blackout(on) {
    const v = on == null ? (S.black ? 0 : 1) : on ? 1 : 0;
    set({ black: v });
    toast(v ? "Blackout" : "Back from black");
  }

  // ---------------------------------------------------------------- knobs and faders (the desk's knob, its own values here)
  const KNOBS = [
    { k: "inten", label: "Intensity", midi: "intensity", lo: 0, hi: 2, def: 1, fmt: (v) => Math.round(v * 100) + "%" },
    { k: "speed", label: "Speed", midi: "speed", lo: 0.25, hi: 2, def: 1, fmt: (v) => v.toFixed(2) + "×" },
    { k: "glow", label: "Glow", midi: "glow", lo: 0, hi: 1, def: 0, fmt: (v) => Math.round(v * 100) + "" },
    { k: "chaos", label: "Chaos", midi: "chaos", lo: 0, hi: 1, def: 0.5, fmt: (v) => Math.round(v * 100) + "" },
  ];
  const ARC = (v) => {
    const a0 = -135, a1 = a0 + 270 * v, r = 25, c = 27, p = (a) => [c + r * Math.sin((a * Math.PI) / 180), c - r * Math.cos((a * Math.PI) / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1), [xe, ye] = p(135);
    return `<path d="M${x0} ${y0} A${r} ${r} 0 1 1 ${xe} ${ye}" stroke="rgba(28,28,30,.1)" stroke-width="3" fill="none" stroke-linecap="round"/>` +
      (v > 0.001 ? `<path d="M${x0} ${y0} A${r} ${r} 0 ${270 * v > 180 ? 1 : 0} 1 ${x1} ${y1}" stroke="url(#pfg)" stroke-width="3" fill="none" stroke-linecap="round"/>` : "");
  };
  const norm = (d, v) => (v - d.lo) / (d.hi - d.lo);
  function buildKnobs() {
    $("knobs").innerHTML = KNOBS.map((d) => `<div class="xf-knob" data-k="${d.k}" data-midi="${d.midi}" role="slider" tabindex="0" aria-label="${d.label}" aria-valuemin="0" aria-valuemax="100" title="${d.label}: drag up or down, double-click to reset">
      <div class="dial"><svg viewBox="0 0 54 54"><defs><linearGradient id="pfg" x1="0" x2="1"><stop offset="0" stop-color="#8f74ff"/><stop offset="1" stop-color="#4b33e6"/></linearGradient></defs></svg><div class="cap"><i></i></div></div><b>${d.label}</b><small></small></div>`).join("");
    paintKnobs();
  }
  function paintKnobs() {
    KNOBS.forEach((d) => {
      const el = document.querySelector(`.xf-knob[data-k="${d.k}"]`);
      if (!el) return;
      const v = Math.max(0, Math.min(1, norm(d, S[d.k])));
      el.setAttribute("aria-valuenow", Math.round(v * 100));
      el.setAttribute("aria-valuetext", d.fmt(S[d.k]));
      const svg = el.querySelector("svg");
      svg.innerHTML = svg.querySelector("defs").outerHTML + ARC(v);
      el.querySelector(".cap i").style.transform = `rotate(${-135 + 270 * v}deg)`;
      el.querySelector("small").textContent = d.fmt(S[d.k]);
    });
  }
  function knob(name, v01) {  // MIDI and the dials: 0..1 onto the parameter's range
    const d = KNOBS.find((x) => x.k === name || x.midi === name);
    if (name === "master") { setMaster(v01); return; }
    if (!d) return;
    set({ [d.k]: +(d.lo + (d.hi - d.lo) * Math.max(0, Math.min(1, v01))).toFixed(3) });
  }
  let drag = null;
  $("knobs").addEventListener("pointerdown", (e) => {
    const el = e.target.closest(".xf-knob");
    if (!el || XenoMidi.learnMode) return;
    const d = KNOBS.find((x) => x.k === el.dataset.k);
    drag = { el, d, y: e.clientY, v: norm(d, S[d.k]) };
    el.setPointerCapture(e.pointerId); e.preventDefault();
  });
  $("knobs").addEventListener("pointermove", (e) => { if (drag) knob(drag.d.k, drag.v + (drag.y - e.clientY) / 160); });
  $("knobs").addEventListener("pointerup", () => { drag = null; });
  $("knobs").addEventListener("dblclick", (e) => { const el = e.target.closest(".xf-knob"); if (!el) return; const d = KNOBS.find((x) => x.k === el.dataset.k); set({ [d.k]: d.def }); });
  $("knobs").addEventListener("wheel", (e) => { const el = e.target.closest(".xf-knob"); if (!el) return; e.preventDefault(); const d = KNOBS.find((x) => x.k === el.dataset.k); knob(d.k, norm(d, S[d.k]) - Math.sign(e.deltaY) * 0.03); }, { passive: false });
  $("knobs").addEventListener("keydown", (e) => {
    const el = e.target.closest(".xf-knob");
    if (!el) return;
    const step = { ArrowUp: 0.04, ArrowRight: 0.04, ArrowDown: -0.04, ArrowLeft: -0.04 }[e.key];
    if (step == null) return;
    e.preventDefault(); e.stopPropagation();
    const d = KNOBS.find((x) => x.k === el.dataset.k);
    knob(d.k, norm(d, S[d.k]) + step);
  });
  function setMaster(v01) { const v = Math.max(0, Math.min(1, v01)); set({ master: +v.toFixed(3) }); }
  $("master").addEventListener("input", (e) => setMaster(e.target.value / 100));
  const LANES = [["drums", "Drums", "#ff8a5c"], ["bass", "Bass", "#7c6cff"], ["other", "Other", "#3ccf8e"], ["vocals", "Vocals", "#f2b14a"]];
  function buildLanes() {
    $("lanes").innerHTML = LANES.map(([k, l, c]) => `<label class="xf-lane" title="${l}"><span><i style="background:${c}"></i>${l}</span>
      <input type="range" min="0" max="100" value="${Math.round(S.gain[k] * 100)}" data-gain="${k}" data-midi="${k}" style="--c:${c};--p:${Math.round(S.gain[k] * 100)}%" aria-label="${l} reaction"><output>${Math.round(S.gain[k] * 100)}</output></label>`).join("");
  }
  $("lanes").addEventListener("input", (e) => { const r = e.target.closest("[data-gain]"); if (r) set({ gain: { [r.dataset.gain]: r.value / 100 } }); });
  function paintLook() {
    $("mir").classList.toggle("on", !!S.mir); $("stb").classList.toggle("on", !!S.stb); $("kal").classList.toggle("on", !!S.kal);
    $("kal").hidden = !EXPERT;
    $("fx").value = S.fx;
    $("hudb").classList.toggle("on", !!S.hud); $("hud").classList.toggle("hide", !S.hud);
    $("master").value = Math.round(S.master * 100); $("master-o").textContent = Math.round(S.master * 100);
    $("blackb").classList.toggle("on", !!S.black); $("blackb").setAttribute("aria-pressed", S.black ? "true" : "false");
    $("pf").classList.toggle("is-black", !!S.black);
    document.querySelectorAll("#lanes [data-gain]").forEach((r) => { const v = Math.round(S.gain[r.dataset.gain] * 100); if (+r.value !== v) r.value = v; r.style.setProperty("--p", v + "%"); r.nextElementSibling.textContent = v; });
    document.querySelectorAll("#pics [data-pics]").forEach((b) => b.classList.toggle("on", b.dataset.pics === S.pics));
    paintKnobs(); paintTransport();
  }

  // ---------------------------------------------------------------- source: the cut, the library, a track, the mic
  const libSpec = () => ({
    vibes: (Q.get("vibes") || DEF_VIBES.join(",")).split(",").filter((v) => v && v !== "none"),
    shots: (Q.get("shots") || "wide,reveal,close,medium").split(","), footage: Q.get("footage") !== "0", max: +(Q.get("footageMax") || 8), seed: +(Q.get("seed") || 7),
  });
  function setSpec(part) {
    Object.assign(C.spec, part);
    send("scenes", C.spec);
    Promise.resolve(S.scenesReady).then(() => { if (!C.padsSet) { C.padsSet = true; loadPads(); } if ($("bank").open) paintBank(); });
  }
  function srcNote(t) { $("src-note").textContent = t || ""; }
  function setSong(song, o) {
    o = o || {};
    if (o.soft && C.song && C.song.src !== "browser" && C.songFor === C.token) return;
    C.song = song; C.songFor = C.token;
    send("song", { song });
    const n = song && song.passages ? song.passages.length : 0;
    $("strip-note").textContent = !song ? "" : song.src === "cut" ? `The cut's own sections, beats and drop · ${n} passage${n === 1 ? "" : "s"}`
      : song.src === "desk" ? `The desk's analysis · ${n} passage${n === 1 ? "" : "s"} · click a section to cue it`
        : "Beats from the browser while the desk analyses the song";
    paintTransport();
  }
  async function deskSong(id) {
    const token = C.token;
    for (const url of [`/api/simple/strip?audio_id=${encodeURIComponent(id)}`, `/api/perform/song/${encodeURIComponent(id)}`]) {
      try {
        const r = await fetch(url);
        if (!r.ok) continue;
        const j = await r.json();
        if (token !== C.token) return;
        setSong({ src: "desk", duration: j.duration, tempo: j.tempo, beats: j.beats || [], bars: j.bars || [], bar_phase: j.bar_phase || 0, passages: j.passages || [], drop: j.drop, wave: j.wave || [] });
        srcNote(""); return true;
      } catch (e) { /* the next route */ }
    }
    srcNote("The desk has no analysis of this song, so the beats come from the browser and there are no sections.");
    return false;
  }
  async function onTrackFile(f) {
    if (!f) return;
    help(false);
    S.trackId = "";
    try { await XC.loadTrack(f); } catch (e) { toast("That file did not play: " + (e.message || e)); return; }
    srcNote("Asking the desk for the song's sections and drops…");
    const token = C.token;
    try {
      const fd = new FormData(); fd.append("file", f, f.name || "track.wav");
      const r = await fetch("/api/analyze", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.status);
      if (token !== C.token) return;
      S.trackId = j.audio_id;
      const u = new URL(location.href); u.searchParams.set("track", j.audio_id); ["job", "stems", "stemsId"].forEach((k) => u.searchParams.delete(k)); history.replaceState(null, "", u.toString());
      await deskSong(j.audio_id);
    } catch (e) { srcNote("The desk did not analyse it (" + (e.message || e) + "), so the beats come from the browser and there are no sections."); }
  }
  function trackLoaded(title, dur) {
    C.token++; C.title = title; C.holds = []; C.cue = null;
    $("pf-song").textContent = `${title} · ${clock(dur)}`;
    $("empty").hidden = true;
    $("trackl").className = "upload";
    paintSource(); paintTransport();
  }
  async function loadJob(id) {
    srcNote("Opening the cut…");
    let j;
    try {
      const r = await fetch("/api/perform/job/" + encodeURIComponent(id));
      j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.status);
    } catch (e) {
      srcNote("That cut did not open (" + (e.message || e) + "): the library loops play instead.");
      S.job = ""; setSpec({ lib: libSpec() }); set({ pics: "lib" }); return;
    }
    C.job = j;
    const cut = j.clips.filter((c) => c.url).map((c) => ({ url: c.url, name: c.to || c.name, key: "clip:" + c.index }));
    setSpec({ cut, lib: libSpec() });
    set({ pics: cut.length ? "cut" : "lib" });
    if (j.stems) stems(j.stems);
    try {
      const b = await (await fetch(j.song)).blob();
      await XC.loadTrack(b, { title: j.title || "This cut", song: true });
    } catch (e) { srcNote("The cut's song did not load: " + (e.message || e)); }
    setSong({ src: "cut", duration: j.duration, tempo: j.tempo, beats: j.beats, bars: j.bars, bar_phase: j.bar_phase, passages: j.passages, drop: j.drop, shots: j.shots });
    $("pf-song").textContent = [j.title || "This cut", j.vibe, clock(j.duration)].filter(Boolean).join(" · ");
    srcNote(j.note || `${cut.length} clips of this cut, then the library loops. Follow the song plays the cut as it was made; hold a pad to show one.`);
  }
  async function stems(url) {
    await XC.loadStems(url);
    send("stems", { url }, { local: false });
    $("stemsb").textContent = "Stems on";
    $("stemsb").classList.add("on");
    $("stems-state").textContent = "from the stems";
  }
  function paintSource() {
    const mic = !!XC.mic;
    document.querySelectorAll("#snd [data-snd]").forEach((b) => b.classList.toggle("on", (b.dataset.snd === "mic") === mic));
    $("input").hidden = !mic;
    const cutBtn = document.querySelector('#pics [data-pics="cut"]');
    cutBtn.disabled = !C.spec.cut.length;
    cutBtn.title = C.spec.cut.length ? "This cut's own clips" : "Open Perform from a cut (Perform it, beside Download) to play its clips";
    $("stemsb").disabled = mic || !XC.file;
  }
  async function micToggle(on) {
    if (on) {
      const ok = await XC.micOn($("input").value);
      if (ok) { help(false); toast("Listening. Beats come from the input; T taps the tempo."); srcNote("The input goes to the beats and into a take, never to the speakers."); }
    } else if (XC.mic) { XC.micOff(); toast("The input is off: the song is the sound again."); srcNote(""); }
    paintSource(); paintTransport();
  }
  function micFailed(why) { toast(why); srcNote(why); paintSource(); }
  $("snd").addEventListener("click", (e) => { const b = e.target.closest("[data-snd]"); if (b) micToggle(b.dataset.snd === "mic"); });
  $("mic2").onclick = () => micToggle(true);
  $("input").onchange = () => { if (XC.mic) micToggle(true); };  // another input while live swaps the source (V10)
  $("pics").addEventListener("click", (e) => { const b = e.target.closest("[data-pics]"); if (b && !b.disabled) set({ pics: b.dataset.pics }); });
  $("track").onchange = (e) => { const f = e.target.files[0]; e.target.value = ""; onTrackFile(f); };
  $("files").onchange = (e) => {
    const fs = [...e.target.files]; e.target.value = "";
    if (!fs.length) return;
    setSpec({ files: C.spec.files.concat(fs) });
    if (S.pics !== "lib") set({ pics: "lib" });
    toast(`${fs.length} loop(s) added`);
  };
  $("stemsb").onclick = () => XC.useStems();

  // ---------------------------------------------------------------- REC (V7): the dot and the timer here, the take in the output
  function rec() {
    if (recording()) { send("rec", { on: false }); return; }
    if (!R().scenes && !track() && !XC.mic) { toast("Load a track (or open the mic) before you record."); return; }
    help(false);
    send("rec", { on: true, title: C.title || "Live take", job: (C.job && C.job.id) || "", audio_id: S.trackId || "", source: XC.mic ? "mic" : S.pics });
    toast(linked() ? "Recording the output window" : "Recording this window's picture");
  }
  function paintRec() {
    const r = R().rec || {}, on = !!r.on;
    $("pf-rec").classList.toggle("is-on", on);
    $("rec-dot").classList.toggle("on", on);
    const b = $("recb");
    b.textContent = on ? "Stop" : "Rec";
    b.classList.toggle("is-rec", on);
    let line = "";
    if (on) line = "REC " + clock(r.secs) + (r.w ? ` · ${r.w}×${r.h}` : "");
    else if (r.status === "saving" || r.status === "remuxing") line = "Saving the take…";
    $("rec-time").textContent = line;
    if (r.err && r.err !== C.recErr) { C.recErr = r.err; toast(r.err); }
    const key = r.take && r.take.id ? r.take.id + ":" + r.take.status : "";
    if (!on && key && key !== C.recSeen && (r.status === "saved" || r.status === "error")) {
      C.recSeen = key; C.lastTake = r.take;
      if (r.take.status === "done") toast(`Take saved · ${clock(r.take.seconds)} · ${r.take.size} · in My videos`);
    }
    const t = C.lastTake;
    $("last-take").innerHTML = t ? `Last take: <a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(clock(t.seconds))} · ${esc(t.size)}</a>${t.status !== "done" ? ` (${esc(t.status)})` : ""}` : "";
  }
  addEventListener("beforeunload", (e) => { if (recording()) { e.preventDefault(); e.returnValue = ""; } });
  // a take cut short (the browser crashed, the machine slept) is on the desk up to its last chunk: finish it into an mp4
  async function recover() {
    try {
      const j = await (await fetch("/api/perform/takes?limit=20")).json();
      for (const t of (j.takes || []).filter((x) => x.status === "interrupted")) {
        const r = await fetch(`/api/perform/takes/${t.id}/finish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (r.ok) { C.lastTake = await r.json(); toast("A take that was cut short is saved up to its last second, in My videos."); }
      }
    } catch (e) { /* an older desk without takes */ }
  }
  $("desk-link").addEventListener("click", (e) => { if (recording() && !confirm("A take is recording. Leave and stop it?")) e.preventDefault(); });

  // ---------------------------------------------------------------- help, toast, HUD, the monitor alone
  function help(on) {
    const el = $("help"), show = on == null ? el.hidden : !!on;
    el.hidden = !show;
    $("helpb").setAttribute("aria-expanded", show ? "true" : "false");
    $("pf").classList.toggle("has-help", show);
  }
  function toast(t) {
    const el = $("toast");
    el.textContent = t;
    el.classList.add("show");
    clearTimeout(C.toastT);
    C.toastT = setTimeout(() => el.classList.remove("show"), 2600);
  }
  function monitorOnly() { C.solo = !C.solo; $("pf").classList.toggle("is-solo", C.solo); toast(C.solo ? "The monitor alone: H brings the panels back" : "Panels back"); }
  function paintHud(r) {
    if (!S.hud) return;
    $("h-fps").textContent = r.fps || 0; $("h-bpm").textContent = (C.song && C.song.tempo) || S.bpm || "-"; $("h-beat").textContent = r.beats || 0;
    document.querySelectorAll("#bars i").forEach((el, i) => el.classList.toggle("on", i === r.bar));
    $("h-scene").textContent = r.scene || "-"; $("h-fx").textContent = (r.auto ? "auto · " : "") + (r.fxName || "-");
    $("h-every").textContent = S.every ? S.every + " beat(s)" : "follow song"; $("h-int").textContent = (+S.inten).toFixed(2);
    const L = r.levels || {}; $("mb").style.height = 3 + 27 * (L.b || 0) + "px"; $("mm").style.height = 3 + 27 * (L.m || 0) + "px"; $("mh").style.height = 3 + 27 * (L.h || 0) + "px";
  }

  // ---------------------------------------------------------------- wiring
  $("outb").onclick = () => openOutput();
  $("fs").onclick = () => fullscreen();
  $("recb").onclick = () => rec();
  $("helpb").onclick = () => help();
  $("helpx").onclick = () => help(false);
  $("playb").onclick = () => togglePlay();
  $("startb").onclick = () => seek(0);
  $("cueb").onclick = () => cueDrop();
  $("tapb").onclick = () => send("tap");
  $("blackb").onclick = () => blackout();
  $("hudb").onclick = () => set({ hud: !S.hud });
  $("every").addEventListener("click", (e) => { const b = e.target.closest("[data-every]"); if (b) set({ every: +b.dataset.every }); });
  $("fx").onchange = (e) => XC.setFx(e.target.value);
  $("mir").onclick = () => set({ mir: S.mir ? 0 : 1 });
  $("stb").onclick = () => set({ stb: S.stb ? 0 : 1 });
  $("kal").onclick = () => { if (EXPERT) set({ kal: S.kal ? 0 : 1 }); };

  // ---------------------------------------------------------------- the loop: what moves on screen
  let lastSlow = 0, lastClock = 0, lastStrip = 0;
  function loop(t) {
    requestAnimationFrame(loop);
    const tr = track();
    if (C.cue && tr && !tr.paused && tr.currentTime >= C.cue.at - 0.012) { const c = C.cue; C.cue = null; tr.currentTime = c.to; toast("Cued " + c.label); }
    if (linked() && C.lastAt && t - C.lastAt > 2500) unlink("lost");
    if (linked() && t - lastClock > 50) {  // the clock for an output that cannot reach this window directly
      lastClock = t;
      bc.postMessage({ t: "clock", c: { pos: tr ? tr.currentTime : 0, playing: !!tr && !tr.paused, at: performance.timeOrigin + performance.now(), dur: tr ? tr.duration : 0, mic: !!XC.mic } });
    }
    if (t - lastStrip > 30) { lastStrip = t; drawStrip(); }  // about 30 a second: the playhead stays smooth, the picture keeps the frames
    if (t - lastSlow > 100) {
      lastSlow = t;
      const r = R();
      paintNow(); paintTransport(); paintRec(); paintHud(r);
      if (linked()) paintOut();
    }
  }

  // ---------------------------------------------------------------- the API vj.html and scripts call
  window.XP = {
    init, send, set, monitor, toast, help, rec, recording, togglePlay, seek, cue, cueDrop, press, release, blackout, knob, openOutput, fullscreen,
    monitorOnly, micFailed, trackLoaded, setSong, stems, report: R, linked, snapshot, song: () => C.song,
    ended() { paintTransport(); },
    // automation: play from start for seconds while recording, resolve with the saved take (perform_check.js)
    async go({ start = 0, seconds = 10 } = {}) {
      const tr = track();
      if (!tr) throw new Error("no track");
      XC.ensureAC(); await XC.ac.resume();
      tr.currentTime = start;
      rec();
      await new Promise((r) => setTimeout(r, 150));
      tr.play();
      await new Promise((r) => setTimeout(r, seconds * 1000));
      tr.pause();
      rec();
      for (let i = 0; i < 1200; i++) { const r = R().rec || {}; if (!r.on && r.status && r.status !== "saving" && r.status !== "remuxing" && r.status !== "recording") return r.take || null; await new Promise((x) => setTimeout(x, 250)); }
      return null;
    },
  };
  VJ.go = (o) => window.XP.go(o);

  function init() {
    $("screen").prepend($("stage"));  // the canvas sits in the monitor; in the output window it fills the screen
    buildKnobs(); buildLanes(); paintLook(); paintOut(); paintSource();
    const last = document.createElement("span"); last.id = "last-take"; last.className = "note pf-last"; $("pf-rec").prepend(last);
    if (S.job) loadJob(S.job);
    else {
      setSpec({ lib: libSpec() });
      if (S.trackId) XC.trackFromDesk(S.trackId).then(() => deskSong(S.trackId)).catch(() => toast("That track is no longer on the desk; load it again"));
    }
    if (Q.get("stems")) { $("stemsb").textContent = "Stems on"; $("stemsb").classList.add("on"); }
    XC.listInputs().catch(() => {});
    recover();
    requestAnimationFrame(loop);
  }
  init();
})();
