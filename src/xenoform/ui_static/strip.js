/* The song strip (docs/UI_REVIEW.md 6.1, the Songline redesign): the song drawn as the one canvas of the desk. Lanes,
   defined once: SECTIONS (the song's passages by role, colour-coded, the drop runs flagged), WAVE, BEATS (bars
   heavier), SHOTS (a block a shot: hatched = sketched from stills, solid = rendered, ! = stale after an edit), INTENSITY
   and OBJECTS (keyframe lanes, drawn from the per-shot values; editing them is round 5), the Draft window (dragged by
   whole beats, Shift a bar, Alt free), a playhead, wheel zoom and a section overview of the whole song above the lanes
   (at phone width the overview is the strip).

   window.XenoStrip.mount(host, model, handlers) draws a model into a host; it can be called on every redraw of the desk
   (render() rebuilds #app) and keeps each strip's zoom, scroll and snap by model.id. Times are song seconds. The strip
   knows nothing of the desk: shots, seams and pins carry the desk's own data-act attributes (model.shots[i].act ...),
   so app.js's click handler acts on them; the strip calls handlers.onSeek(t), handlers.onWindow(start) and
   handlers.onPassage(index) for what only it can measure. No picture is rendered here and nothing is fetched. */
(function () {
  "use strict";

  const VIEWS = new Map();   // model.id -> { zoom, t0, snap, fitted }
  const MODELS = new Map();  // model.id -> { model, handlers }
  const LANES = { sections: "Sections", wave: "Wave", beats: "Beats", shots: "Shots", intensity: "Intensity", objects: "Objects" };
  const ROLE_NAMES = { intro: "intro", calm: "calm", sustain: "sustain", build: "build", release: "release", drop: "drop",
    drop_late: "drop", outro: "outro" };
  const MAX_SPAN_S = 4;      // zoomed all the way in, about four seconds across the view

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }
  function clock(t) {
    const s = Math.max(0, Math.round(Number(t) || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }
  function pos(t, dur) {
    return `${((100 * Math.max(0, Math.min(dur, Number(t) || 0))) / Math.max(1e-6, dur)).toFixed(4)}%`;
  }
  function span(a, b, dur) {
    const lo = Math.max(0, Math.min(dur, Number(a) || 0));
    const hi = Math.max(lo, Math.min(dur, Number(b) || 0));
    return `${((100 * (hi - lo)) / Math.max(1e-6, dur)).toFixed(4)}%`;
  }
  function attrs(map) {
    if (!map) return "";
    return Object.keys(map).filter((k) => map[k] != null && map[k] !== false)
      .map((k) => ` ${k}="${esc(map[k] === true ? "" : map[k])}"`).join("");
  }
  function view(id) {
    if (!VIEWS.has(id)) VIEWS.set(id, { zoom: 1, t0: 0, snap: "beat", fitted: "" });
    return VIEWS.get(id);
  }
  function hueOf(model, role) {
    const hues = model.hues || {};
    return hues[role] != null ? hues[role] : 260;
  }
  function median(list) {
    const gaps = [];
    for (let i = 1; i < list.length; i += 1) if (list[i] > list[i - 1]) gaps.push(list[i] - list[i - 1]);
    gaps.sort((a, b) => a - b);
    return gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0.5;
  }
  function nearest(list, t) {
    if (!list || !list.length) return t;
    let lo = 0;
    let hi = list.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (list[mid] <= t) lo = mid; else hi = mid;
    }
    return Math.abs(list[lo] - t) <= Math.abs(list[hi] - t) ? list[lo] : list[hi];
  }
  // where a time lands under the snap: the nearest beat (the default), the nearest bar line (Shift, or Snap: Bar), or
  // anywhere (Alt, or Snap: Free)
  function snapTime(model, t, mode) {
    if (mode === "free") return t;
    const grid = mode === "bar" ? model.bars : model.beats;
    return grid && grid.length ? nearest(grid, t) : t;
  }
  function snapMode(v, event) {
    if (event && event.altKey) return "free";
    if (event && event.shiftKey) return "bar";
    return v.snap || "beat";
  }

  // ------------------------------------------------------------------ the markup
  function waveSvg(model) {
    const peaks = model.wave || [];
    const dur = model.duration;
    if (!peaks.length || !dur) return "";
    const w = dur * 100;
    const n = peaks.length;
    const top = [];
    const bottom = [];
    for (let i = 0; i < n; i += 1) {
      const x = ((i + 0.5) / n) * w;
      const v = Math.max(0.02, Math.min(1, Number(peaks[i]) || 0));
      top.push(`${x.toFixed(1)} ${(50 - v * 46).toFixed(1)}`);
      bottom.push(`${x.toFixed(1)} ${(50 + v * 46).toFixed(1)}`);
    }
    const d = `M0 50 L${top.join(" L")} L${w.toFixed(1)} 50 L${bottom.reverse().join(" L")} Z`;
    return `<svg class="xs-svg" viewBox="0 0 ${w.toFixed(1)} 100" preserveAspectRatio="none" aria-hidden="true"><path d="${d}"/></svg>`;
  }
  function beatsSvg(model) {
    const dur = model.duration;
    const w = dur * 100;
    const bars = new Set((model.bars || []).map((t) => Math.round(t * 100)));
    const beat = [];
    const bar = [];
    (model.beats || []).forEach((t) => {
      const x = Math.round(t * 100);
      (bars.has(x) ? bar : beat).push(`M${x} 0V100`);
    });
    return `<svg class="xs-svg" viewBox="0 0 ${w.toFixed(1)} 100" preserveAspectRatio="none" aria-hidden="true">
      <path class="xs-beat" d="${beat.join("")}"/><path class="xs-bar" d="${bar.join("")}"/></svg>`;
  }
  function intensitySvg(model) {
    const rows = (model.intensity || []).filter((r) => r && r.end > r.start);
    if (!rows.length) return "";
    const w = model.duration * 100;
    const y = (v) => (100 - 8 - Math.max(0, Math.min(1, Number(v) || 0)) * 84).toFixed(1);
    const line = [];
    rows.forEach((r, i) => {
      const x0 = (r.start * 100).toFixed(1);
      const x1 = (r.end * 100).toFixed(1);
      line.push(`${i ? "L" : "M"}${x0} ${y(r.v)} L${x1} ${y(r.v)}`);
    });
    const first = rows[0];
    const last = rows[rows.length - 1];
    const area = `${line.join(" ")} L${(last.end * 100).toFixed(1)} 100 L${(first.start * 100).toFixed(1)} 100 Z`;
    return `<svg class="xs-svg" viewBox="0 0 ${w.toFixed(1)} 100" preserveAspectRatio="none" aria-hidden="true">
      <path class="xs-int-area" d="${area}"/><path class="xs-int-line" d="${line.join(" ")}"/></svg>`;
  }
  function sectionsHtml(model, overview) {
    const dur = model.duration;
    let drops = 0;
    return (model.passages || []).map((p, i) => {
      const hue = hueOf(model, p.role);
      const isDrop = p.drop_run != null;
      if (isDrop) drops += 1;
      const name = p.name || (isDrop ? `drop ${drops}` : (ROLE_NAMES[p.role] || p.role || ""));
      const heat = isDrop && p.heat != null ? ` · drop ${drops}, heat ${Number(p.heat).toFixed(2)}` : "";
      const title = `${name}${p.main ? " · the main drop" : ""} · ${clock(p.start)} to ${clock(p.end)}${heat}${p.more || ""}`;
      const cls = `xs-pass${isDrop ? " is-drop" : ""}${p.main ? " is-main" : ""}`;
      const flag = isDrop ? `<b class="xs-flag" aria-hidden="true">${p.main ? "▼" : "▽"}</b>` : "";
      const tag = overview ? "span" : "button";
      const act = overview ? "" : ` type="button" data-xs="passage" data-index="${i}" data-at="${p.start}"`;
      return `<${tag} class="${cls}"${act} style="left:${pos(p.start, dur)};width:${span(p.start, p.end, dur)};--hue:${hue}" title="${esc(title)}" aria-label="${esc(title)}">${flag}<i>${esc(name)}</i></${tag}>`;
    }).join("");
  }
  function shotsHtml(model) {
    const dur = model.duration;
    const shots = model.shots || [];
    const blocks = shots.map((s) => {
      const hue = hueOf(model, s.section);
      const cls = `xs-shot is-${s.state || "sketch"}${s.picked ? " is-picked" : ""}${s.held ? " is-held" : ""}${s.edited ? " is-edited" : ""}${s.dropped ? " is-dropped" : ""}`;
      const thumb = s.thumb ? `;--thumb:url('${String(s.thumb).replace(/'/g, "%27")}')` : "";
      const label = s.label ? `<i>${esc(s.label)}</i>` : "";
      const badge = s.state === "stale" ? `<b class="xs-stale" title="Changed since it was rendered: re-cut or re-render to see it">!</b>` : "";
      const style = s.style ? `<b class="xs-style">${esc(s.style)}</b>` : "";
      const rest = s.rest ? `<b class="xs-rest">rest</b>` : "";  // Breathe: the object dwells here after its morph
      return `<button type="button" class="${cls}"${attrs(s.act)} style="left:${pos(s.start, dur)};width:${span(s.start, s.end, dur)};--hue:${hue}${thumb}" title="${esc(s.title || "")}" aria-label="${esc(s.title || `Shot ${s.n || ""}`)}"${s.picked ? ' aria-pressed="true"' : ""}><b class="xs-n">${esc(s.n != null ? s.n : "")}</b>${style}${rest}${badge}${label}</button>`;
    }).join("");
    const spans = (model.spans || []).map((o) => `<span class="xs-span is-${esc(o.kind || "run")}" style="left:${pos(o.start, dur)};width:${span(o.start, o.end, dur)}" title="${esc(o.title || "")}"></span>`).join("");
    const seams = shots.filter((s, i) => i > 0 && s.seam).map((s) => {
      const cls = `xs-seam${s.seam.cut ? " is-cut" : ""}${s.seam.dressed ? " is-dressed" : ""}${s.seam.edited ? " is-edited" : ""}${s.seam.picked ? " is-picked" : ""}`;
      return `<button type="button" class="${cls}"${attrs(s.seam.act)} style="left:${pos(s.start, dur)}" title="${esc(s.seam.title || "")}" aria-label="${esc(s.seam.title || "The join")}"><span>${s.seam.dressed ? "◆" : ""}</span></button>`;
    }).join("");
    return blocks + seams + spans;
  }
  function objectsHtml(model) {
    const dur = model.duration;
    return (model.objects || []).map((o) => {
      const img = o.thumb ? `<img src="${esc(o.thumb)}" alt="" loading="lazy" decoding="async">` : "";
      const cls = `xs-pin${o.pinned ? " is-pinned" : ""}${o.picked ? " is-picked" : ""}`;
      const tag = o.act ? "button" : "span";
      return `<${tag}${o.act ? ' type="button"' : ""} class="${cls}"${attrs(o.act)} style="left:${pos(o.t, dur)}" title="${esc(o.title || o.noun || "")}" aria-label="${esc(o.title || o.noun || "")}">${img}<i>${esc(o.noun || "")}</i></${tag}>`;
    }).join("");
  }
  function windowHtml(model, where) {
    const w = model.window;
    if (!w || !(w.end > w.start)) return "";
    const dur = model.duration;
    const grip = w.drag
      ? `<button type="button" class="xs-grip" data-xs="window" aria-label="${esc(`${w.label || "The Draft window"}: drag it along the song, or use the arrow keys (a beat; Shift, a bar)`)}" title="Drag to make the Draft of another stretch: it snaps to the beat (Shift: the bar, Alt: free)"><span>${esc(w.label || "Draft")}</span></button>`
      : `<span class="xs-grip is-fixed"><span>${esc(w.label || "Draft")}</span></span>`;
    return `<div class="xs-window${where === "map" ? " in-map" : ""}" style="left:${pos(w.start, dur)};width:${span(w.start, w.end, dur)}">${where === "map" ? "" : grip}</div>`;
  }
  function mapHtml(model) {
    const dur = model.duration;
    const shots = (model.shots || []).length
      ? `<span class="xs-map-shots" style="left:${pos(model.shots[0].start, dur)};width:${span(model.shots[0].start, model.shots[model.shots.length - 1].end, dur)}"></span>`
      : "";
    const done = (model.shots || []).filter((s) => s.state === "done" || s.state === "stale").length;
    const fill = model.shots && model.shots.length && done
      ? `<span class="xs-map-done" style="left:${pos(model.shots[0].start, dur)};width:${span(model.shots[0].start, model.shots[Math.min(model.shots.length, done) - 1].end, dur)}"></span>` : "";
    return `<div class="xs-map" data-xs="map" aria-label="The whole song: click to look there">
        <div class="xs-map-pass">${sectionsHtml(model, true)}</div>
        ${shots}${fill}
        ${windowHtml(model, "map")}
        <span class="xs-map-view" aria-hidden="true"></span>
        <span class="xs-map-head" aria-hidden="true"></span>
      </div>`;
  }
  function html(model, v) {
    const lanes = (model.lanes || ["sections", "wave", "beats", "shots", "intensity", "objects"]).filter((k) => LANES[k]);
    const dur = model.duration;
    const ghost = !!model.ghost || !(dur > 0);
    const snap = ["beat", "bar", "free"].map((m) => `<button type="button" class="${v.snap === m ? "on" : ""}" data-xs="snap" data-value="${m}" aria-pressed="${v.snap === m ? "true" : "false"}">${m === "beat" ? "Beat" : m === "bar" ? "Bar" : "Free"}</button>`).join("");
    const tools = ghost ? "" : `<span class="xs-tools">
        <span class="xs-snap-label">Snap</span><span class="toggle xs-snap" role="group" aria-label="Snap">${snap}</span>
        <span class="xs-zoom" role="group" aria-label="Zoom"><button type="button" class="text" data-xs="zoom-out" aria-label="Zoom out" title="Zoom out (or the wheel over the strip)">−</button><button type="button" class="text" data-xs="fit" title="The whole song">Fit</button><button type="button" class="text" data-xs="zoom-in" aria-label="Zoom in" title="Zoom in (or the wheel over the strip)">+</button></span>
      </span>`;
    const head = `<div class="xs-head"><span class="xs-title">${model.title || ""}</span>${model.badge ? `<span class="xs-badge">${esc(model.badge)}</span>` : ""}${tools}</div>`;
    if (ghost) {
      const rows = lanes.map((k) => `<div class="xs-lane xs-${k}"></div>`).join("");
      return `${head}<div class="xs-body is-ghost"><div class="xs-labels" aria-hidden="true">${lanes.map((k) => `<span class="xs-lab-${k}">${LANES[k]}</span>`).join("")}</div>
        <div class="xs-view"><div class="xs-track" style="width:100%">${rows}<div class="xs-ghost-note">${model.ghostNote || ""}</div></div></div></div>`;
    }
    const lane = (k) => {
      if (k === "sections") return `<div class="xs-lane xs-sections" aria-label="Sections">${sectionsHtml(model)}</div>`;
      if (k === "wave") return `<div class="xs-lane xs-wave" data-xs="seek">${waveSvg(model)}</div>`;
      if (k === "beats") return `<div class="xs-lane xs-beats" data-xs="seek">${beatsSvg(model)}</div>`;
      if (k === "shots") return `<div class="xs-lane xs-shots" aria-label="Shots">${shotsHtml(model)}${(model.shots || []).length ? "" : `<span class="xs-empty">${esc(model.shotsNote || "")}</span>`}</div>`;
      if (k === "intensity") return `<div class="xs-lane xs-intensity" data-xs="seek">${intensitySvg(model)}</div>`;
      if (k === "objects") return `<div class="xs-lane xs-objects" aria-label="Objects">${objectsHtml(model)}</div>`;
      return "";
    };
    const marks = (model.marks || []).map((m) => `<span class="xs-mark${m.kind ? ` is-${esc(m.kind)}` : ""}" style="left:${pos(m.t, dur)}" title="${esc(m.title || "")}"></span>`).join("");
    const body = `<div class="xs-body">
        <div class="xs-labels" aria-hidden="true">${lanes.map((k) => `<span class="xs-lab-${k}">${LANES[k]}</span>`).join("")}</div>
        <div class="xs-view" tabindex="-1">
          <div class="xs-track" style="width:${(100 * v.zoom).toFixed(3)}%">
            ${lanes.map(lane).join("")}
            ${marks}
            ${windowHtml(model, "track")}
            <span class="xs-playhead" aria-hidden="true"${model.playhead != null ? ` style="left:${pos(model.playhead, dur)}"` : ""}></span>
          </div>
        </div>
      </div>`;
    return `${head}${mapHtml(model)}${body}${model.foot ? `<p class="xs-foot">${model.foot}</p>` : ""}`;
  }

  // ------------------------------------------------------------------ the view: zoom and scroll
  function parts(host) {
    return {
      viewEl: host.querySelector(".xs-view"),
      track: host.querySelector(".xs-track"),
      frame: host.querySelector(".xs-map-view"),
      map: host.querySelector(".xs-map"),
    };
  }
  function maxZoom(model) {
    return Math.max(1, Math.min(96, (Number(model.duration) || 1) / MAX_SPAN_S));
  }
  function applyView(host, model, v) {
    const { viewEl, track } = parts(host);
    if (!viewEl || !track || model.ghost) return;
    track.style.width = `${(100 * v.zoom).toFixed(3)}%`;
    const width = track.getBoundingClientRect().width || viewEl.clientWidth || 1;
    viewEl.scrollLeft = (v.t0 / Math.max(1e-6, model.duration)) * width;
    paintFrame(host, model, v);
    density(host, model, width);
  }
  // how dense the grid is at this zoom: beat ticks fade out under 5 px apart, object names show when they fit
  function density(host, model, width) {
    const strip = host.querySelector(".xs") || host;
    const pxPerS = width / Math.max(1e-6, model.duration);
    strip.classList.toggle("xs-dense", median(model.beats || []) * pxPerS < 5);
    const pins = (model.objects || []).map((o) => o.t).sort((a, b) => a - b);
    let gap = Infinity;
    for (let i = 1; i < pins.length; i += 1) gap = Math.min(gap, pins[i] - pins[i - 1]);
    strip.classList.toggle("xs-roomy", pins.length < 2 || gap * pxPerS > 74);
  }
  function paintFrame(host, model, v) {
    const { viewEl, track, frame } = parts(host);
    if (!frame || !viewEl || !track) return;
    const width = track.getBoundingClientRect().width || 1;
    const t0 = (viewEl.scrollLeft / width) * model.duration;
    const t1 = ((viewEl.scrollLeft + viewEl.clientWidth) / width) * model.duration;
    frame.style.left = pos(t0, model.duration);
    frame.style.width = span(t0, t1, model.duration);
    frame.hidden = v.zoom <= 1.001;
  }
  function zoomAt(host, model, v, factor, clientX) {
    const { viewEl, track } = parts(host);
    if (!viewEl || !track) return;
    const box = viewEl.getBoundingClientRect();
    const x = clientX == null ? box.width / 2 : Math.max(0, Math.min(box.width, clientX - box.left));
    const width = track.getBoundingClientRect().width || 1;
    const at = ((viewEl.scrollLeft + x) / width) * model.duration;
    const next = Math.max(1, Math.min(maxZoom(model), v.zoom * factor));
    if (Math.abs(next - v.zoom) < 1e-4) return;
    v.zoom = next;
    track.style.width = `${(100 * v.zoom).toFixed(3)}%`;
    const nextWidth = track.getBoundingClientRect().width || 1;
    viewEl.scrollLeft = (at / model.duration) * nextWidth - x;
    v.t0 = (viewEl.scrollLeft / nextWidth) * model.duration;
    paintFrame(host, model, v);
    density(host, model, nextWidth);
  }
  // zoom so [a, b] fills most of the view, with a little of the song either side
  function fitTo(host, model, v, a, b) {
    const dur = Number(model.duration) || 1;
    const lo = Math.max(0, Math.min(a, b));
    const hi = Math.min(dur, Math.max(a, b));
    const len = Math.max(MAX_SPAN_S, (hi - lo) * 1.5);
    v.zoom = Math.max(1, Math.min(maxZoom(model), dur / len));
    v.t0 = Math.max(0, Math.min(dur - dur / v.zoom, lo - (len - (hi - lo)) / 2));
    if (host) applyView(host, model, v);
  }

  // ------------------------------------------------------------------ mount
  function mount(host, model, handlers) {
    if (!host || !model) return;
    const id = String(model.id || "strip");
    const v = view(id);
    MODELS.set(id, { model, handlers: handlers || {} });
    v.zoom = Math.min(v.zoom, maxZoom(model));
    const strip = document.createElement("div");
    strip.className = `xs${model.overview ? " xs-overview" : ""}${model.ghost ? " xs-ghost" : ""}${model.busy ? " xs-busy" : ""}`;
    strip.dataset.stripId = id;
    if (model.label) strip.setAttribute("aria-label", model.label);
    strip.innerHTML = html(model, v);
    host.replaceChildren(strip);
    // the first sight of a focus span (the Draft window, the cut): zoom to it once, then the strip is yours
    const fitKey = JSON.stringify([Math.round(model.duration * 10), model.focus || null]);
    if (model.focus && v.fitted !== fitKey && !model.overview) {
      v.fitted = fitKey;
      fitTo(host, model, v, model.focus[0], model.focus[1]);
    } else applyView(host, model, v);
    const viewEl = host.querySelector(".xs-view");
    if (viewEl) {
      viewEl.addEventListener("scroll", () => {
        const track = host.querySelector(".xs-track");
        const width = (track && track.getBoundingClientRect().width) || 1;
        v.t0 = (viewEl.scrollLeft / width) * model.duration;
        paintFrame(host, model, v);
      }, { passive: true });
      viewEl.addEventListener("wheel", (event) => {
        if (model.ghost) return;
        if (event.ctrlKey && !event.deltaY) return;
        const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY);
        if (horizontal) return;  // a trackpad's sideways swipe pans natively
        event.preventDefault();
        if (event.shiftKey) {  // Shift + wheel pans
          viewEl.scrollLeft += event.deltaY;
          return;
        }
        zoomAt(host, model, v, Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0018)), event.clientX);
      }, { passive: false });
    }
    if (model.playhead != null) setPlayhead(id, model.playhead);
  }

  function hostOf(id) {
    const strip = document.querySelector(`.xs[data-strip-id="${CSS.escape(id)}"]`);
    return strip ? strip.parentElement : null;
  }

  // the playhead, moved without a redraw (the player's clock, the sketch's); follow keeps it on screen while it plays
  function setPlayhead(id, t, follow) {
    const host = hostOf(id);
    const entry = MODELS.get(id);
    if (!host || !entry) return;
    const model = entry.model;
    const dur = model.duration;
    const head = host.querySelector(".xs-playhead");
    const mapHead = host.querySelector(".xs-map-head");
    const on = t != null && Number.isFinite(Number(t));
    if (head) {
      head.classList.toggle("on", on);
      if (on) head.style.left = pos(t, dur);
    }
    if (mapHead) {
      mapHead.classList.toggle("on", on);
      if (on) mapHead.style.left = pos(t, dur);
    }
    model.playhead = on ? Number(t) : null;
    if (!on || !follow) return;
    const { viewEl, track } = parts(host);
    if (!viewEl || !track) return;
    const width = track.getBoundingClientRect().width || 1;
    const x = (Number(t) / dur) * width;
    if (x < viewEl.scrollLeft + 8 || x > viewEl.scrollLeft + viewEl.clientWidth - 24) {
      viewEl.scrollLeft = Math.max(0, x - viewEl.clientWidth * 0.15);
    }
  }

  // ------------------------------------------------------------------ input: clicks, the window drag, keys
  function entryOf(node) {
    const strip = node && node.closest ? node.closest(".xs[data-strip-id]") : null;
    if (!strip) return null;
    const id = strip.dataset.stripId;
    const entry = MODELS.get(id);
    return entry ? { id, strip, host: strip.parentElement, model: entry.model, handlers: entry.handlers, v: view(id) } : null;
  }
  function timeAt(container, model, clientX) {
    const box = container.getBoundingClientRect();
    return Math.max(0, Math.min(model.duration, ((clientX - box.left) / Math.max(1, box.width)) * model.duration));
  }
  function moveWindow(e, start) {
    const w = e.model.window;
    if (!w) return;
    const len = w.end - w.start;
    const at = Math.max(0, Math.min(e.model.duration - len, start));
    e.strip.querySelectorAll(".xs-window").forEach((node) => {
      node.style.left = pos(at, e.model.duration);
    });
    const label = e.strip.querySelector(".xs-grip span");
    if (label) label.textContent = `${(w.label || "Draft").split(" · ")[0]} · ${clock(at)} to ${clock(at + len)}`;
    return at;
  }

  let drag = null;
  document.addEventListener("pointerdown", (event) => {
    const grip = event.target.closest && event.target.closest(".xs [data-xs=window]");
    const map = !grip && event.target.closest && event.target.closest(".xs [data-xs=map]");
    if (!grip && !map) return;
    const e = entryOf(event.target);
    if (!e || !e.model.window) {
      if (map && e) centerOn(e, timeAt(map, e.model, event.clientX));
      return;
    }
    if (map) {
      centerOn(e, timeAt(map, e.model, event.clientX));
      return;
    }
    const track = e.strip.querySelector(".xs-track");
    drag = { e, x: event.clientX, start: e.model.window.start, width: (track && track.getBoundingClientRect().width) || 1, moved: false, at: e.model.window.start };
    grip.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  document.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    if (!drag.moved && Math.abs(dx) < 3) return;
    drag.moved = true;
    const t = drag.start + (dx / drag.width) * drag.e.model.duration;
    drag.at = moveWindow(drag.e, snapTime(drag.e.model, t, snapMode(drag.e.v, event)));
    drag.e.strip.classList.add("xs-dragging");
  });
  document.addEventListener("pointerup", () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    d.e.strip.classList.remove("xs-dragging");
    if (d.moved && Math.abs(d.at - d.start) > 1e-3 && d.e.handlers.onWindow) d.e.handlers.onWindow(d.at);
  });
  function centerOn(e, t) {
    const { viewEl, track } = parts(e.host);
    if (!viewEl || !track) {
      if (e.handlers.onSeek) e.handlers.onSeek(t);
      return;
    }
    const width = track.getBoundingClientRect().width || 1;
    viewEl.scrollLeft = Math.max(0, (t / e.model.duration) * width - viewEl.clientWidth / 2);
  }

  document.addEventListener("click", (event) => {
    const node = event.target.closest && event.target.closest(".xs [data-xs]");
    if (!node) return;
    const e = entryOf(node);
    if (!e) return;
    const what = node.dataset.xs;
    if (what === "snap") {
      e.v.snap = node.dataset.value || "beat";
      e.strip.querySelectorAll("[data-xs=snap]").forEach((b) => {
        const on = b.dataset.value === e.v.snap;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    } else if (what === "zoom-in" || what === "zoom-out") {
      zoomAt(e.host, e.model, e.v, what === "zoom-in" ? 1.6 : 1 / 1.6, null);
    } else if (what === "fit") {
      e.v.zoom = 1;
      e.v.t0 = 0;
      applyView(e.host, e.model, e.v);
    } else if (what === "passage") {
      const i = Number(node.dataset.index);
      if (e.handlers.onPassage) e.handlers.onPassage(i, (e.model.passages || [])[i]);
      else if (e.handlers.onSeek) e.handlers.onSeek(Number(node.dataset.at) || 0);
    } else if (what === "seek") {
      const t = timeAt(e.strip.querySelector(".xs-track") || node, e.model, event.clientX);
      if (e.handlers.onSeek) e.handlers.onSeek(t);
    }
  });

  document.addEventListener("keydown", (event) => {
    const grip = event.target && event.target.closest && event.target.closest(".xs [data-xs=window]");
    if (!grip || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
    const e = entryOf(grip);
    if (!e || !e.model.window) return;
    event.preventDefault();
    const grid = event.shiftKey ? e.model.bars : e.model.beats;
    const step = median(grid || []) || 0.5;
    const t = snapTime(e.model, e.model.window.start + (event.key === "ArrowRight" ? step : -step), event.shiftKey ? "bar" : "beat");
    const at = moveWindow(e, t);
    if (e.handlers.onWindow && at != null) e.handlers.onWindow(at);
  });

  window.XenoStrip = {
    mount,
    setPlayhead,
    snapTime,
    view: (id) => Object.assign({}, view(String(id || "strip"))),
    reveal(id, a, b) {
      const host = hostOf(String(id));
      const entry = MODELS.get(String(id));
      if (host && entry) fitTo(host, entry.model, view(String(id)), a, b);
    },
  };
})();
