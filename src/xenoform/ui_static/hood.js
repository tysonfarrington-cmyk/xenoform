/* Under the hood (docs/UI_REVIEW.md 6.4, T4): one click from a shot to every value its morph was rendered with, beside
   what the vibe's preset gives it, editable and re-rendered on the GPU; with no shot chosen, the cut's own rows (aspect,
   model, GPU, where it renders, and the rest of Fine-tune and Work in progress), each saying where it lives and what
   it costs.

   window.XenoHood.mount(host, opts) draws the panel into ``host``; nothing here assumes where that is (the timeline's
   drawer today, the strip's inspector next):
     opts.jobId       the cut (its job id)
     opts.shotIndex   a shot, 0-based, or null for the project scope
     opts.layer       a Stems cut's layer, when the cut has layers
     opts.onRerender  (body, info) => Promise<boolean>: starts the re-render (the desk's postCutEdit, progress on the
                      shot's tile); without it the panel posts /rerender itself and follows the job
     opts.onTake      (n, info) => Promise<boolean>: puts take n back (no render, a re-cut); same fallback
     opts.onSelect    (index) => void: another shot (a slot that plays another shot's morph)
     opts.project     () => ({rows, note}): the project scope's rows: {key, label, value, choices: [{value, label, on}],
                      act (the data-act its chips send), where, cost, hint, link: {label, act, hash, href}}; a project
                      mount without it leaves the host as its page drew it
   window.XenoHood.progress(jobId, {shot, progress, detail, status}) paints a running edit in the panels of that cut.
   window.XenoHood.invalidate(jobId) forgets what was read for the cut, so the next mount reads it again (an edit landed).
*/
(function () {
  "use strict";

  const cache = new Map();    // "job|layer|shot" -> the panel's state: the recipe, the edits waiting, notes
  const running = new Map();  // job -> the edit running on it: {shot, progress, detail, status}
  const EDITABLE = ["prompt", "negative", "seed", "steps", "cfg", "frames", "guide_start", "guide_end", "compression", "style", "lora"];
  const SENT = ["prompt", "negative", "steps", "cfg", "frames", "guide_start", "guide_end", "compression"];

  function api(path, options) {
    const base = window.XENO_BASE || "";
    return window.fetch(/^https?:/.test(path) ? path : base + path, options);
  }
  function media(path) {
    const base = window.XENO_BASE || "";
    if (!path || /^https?:/.test(path)) return path || "";
    return base && path.startsWith("/") && !path.startsWith(base + "/") ? base + path : path;
  }
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function clock(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }
  function secs(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    return s >= 90 ? `about ${clock(s)}` : `about ${s} s`;
  }
  function same(a, b) {
    if (a == null || b == null) return a == b;  // eslint-disable-line eqeqeq
    if (typeof a === "number" || typeof b === "number") return Math.abs(Number(a) - Number(b)) < 1e-6;
    if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => same(x, b[i]));
    if (typeof a === "object") return same(a.name, b.name) && same(Number(a.strength), Number(b.strength));
    return String(a).trim() === String(b).trim();
  }
  function keyOf(o) {
    return `${o.jobId}|${o.layer || ""}|${o.shotIndex}`;
  }
  function q(params) {
    const parts = Object.entries(params).filter(([, v]) => v != null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
    return parts.length ? `?${parts.join("&")}` : "";
  }

  // ------------------------------------------------------------------------------------------ the values

  function used(entry, k) {
    const r = entry.recipe || {};
    const u = r.used || {};
    const p = entry.preset || r.preset || {};
    if (k === "style") return u.style || p.style || "melt";
    if (k === "lora") return u.lora || null;
    return u[k] !== undefined && u[k] !== null ? u[k] : p[k];
  }
  function current(entry, k) {
    if (Object.prototype.hasOwnProperty.call(entry.edits, k)) return entry.edits[k];
    if (k === "prompt" && entry.follow && (entry.preset || (entry.recipe || {}).preset)) return (entry.preset || entry.recipe.preset).prompt;
    return used(entry, k);
  }
  function presetOf(entry, k) {
    const p = entry.preset || (entry.recipe || {}).preset;
    if (!p) return undefined;
    if (k === "style") return p.style;
    if (k === "lora") return null;
    return p[k];
  }
  function pending(entry) {
    return EDITABLE.filter((k) => Object.prototype.hasOwnProperty.call(entry.edits, k) && !same(entry.edits[k], used(entry, k)))
      .concat(entry.follow && !same(current(entry, "prompt"), used(entry, "prompt")) && !Object.prototype.hasOwnProperty.call(entry.edits, "prompt") ? ["prompt"] : []);
  }
  // The re-render's body: every value that should differ from the preset (so a take's own values survive the next try,
  // the round trip), the style when it changes, the seed kept when anything else changes; nothing changed is another take
  // with the next seed.
  function bodyOf(entry, opts) {
    const r = entry.recipe || {};
    const body = { shot: Number(opts.shotIndex) };
    if (opts.layer) body.layer = opts.layer;
    const changed = pending(entry);
    const hasPreset = !!(entry.preset || r.preset);
    SENT.forEach((k) => {
      const want = current(entry, k);
      if (want === undefined || want === null || want === "") return;
      if (k === "prompt" && entry.follow && !Object.prototype.hasOwnProperty.call(entry.edits, "prompt")) return;  // the style's own words
      if (hasPreset ? !same(want, presetOf(entry, k)) : changed.includes(k)) body[k] = want;
    });
    const lora = current(entry, "lora");
    if (lora && lora.name) {
      body.lora = lora.name;
      body.lora_strength = Number(lora.strength == null ? 1 : lora.strength);
    }
    const style = current(entry, "style");
    if (style && !same(style, used(entry, "style"))) body.style = style;
    if (changed.length) body.seed = Number(current(entry, "seed"));
    return { body, changed };
  }

  // ------------------------------------------------------------------------------------------ loading

  async function load(entry, opts, style) {
    entry.status = entry.recipe ? "ready" : "loading";
    try {
      const res = await api(`/api/jobs/${encodeURIComponent(opts.jobId)}/shots/${Number(opts.shotIndex)}/recipe${q({ style, layer: opts.layer })}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Under the hood could not read this shot.");
      if (style) {
        entry.preset = data.preset || null;  // the preset for the style chosen, its prompt among it
      } else {
        entry.recipe = data;
        entry.preset = data.preset || null;
        entry.follow = !(data.differs && data.differs.prompt);  // the take's words were the style's own: they follow it
        entry.status = "ready";
      }
    } catch (err) {
      entry.status = entry.recipe ? "ready" : "error";
      entry.error = String(err.message || err);
    }
    redraw(entry);
  }

  // ------------------------------------------------------------------------------------------ drawing a shot

  function mark(entry, k) {
    const p = presetOf(entry, k);
    const cur = current(entry, k);
    const wait = pending(entry).includes(k);
    const differs = p !== undefined && !same(cur, p);
    return { wait, differs, cls: `${differs ? " differs" : ""}${wait ? " waiting" : ""}`, sign: wait ? "edited" : differs ? "*" : p !== undefined ? "=" : "" };
  }
  function ghost(entry, k, text) {
    const m = mark(entry, k);
    if (!m.differs) return "";
    return `<span class="hood-preset">preset: ${esc(text)}</span>`;
  }
  function stillName(s) {
    if (!s) return "";
    const f = String(s.file || "").split("/").pop();
    return s.noun ? `${s.noun}${f ? ` <small>${esc(f)}</small>` : ""}` : esc(f);
  }
  function row(entry, k, label, value, extra) {
    const hints = (entry.recipe && entry.recipe.hints) || {};
    const m = k ? mark(entry, k) : { cls: "", sign: "" };
    const id = `hood-${k || label.toLowerCase().replace(/\W+/g, "-")}-${entry.uid}`;
    return `<div class="hood-row${m.cls}" data-hood-row="${esc(k || "")}">
        <label class="hood-label" for="${id}">${esc(label)}</label>
        <div class="hood-value">${value.replace("%ID%", id)}${extra || ""}</div>
        <span class="hood-mark" title="${m.sign === "*" ? "differs from the preset" : m.sign === "=" ? "as the preset" : m.sign === "edited" ? "changed here, not rendered yet" : ""}">${esc(m.sign)}</span>
        ${hints[k] ? `<p class="hood-hint">${esc(hints[k])}</p>` : ""}
      </div>`;
  }
  function framesLabel(n, fps) {
    return `${n} frames · ${((Number(n) - 1) / (Number(fps) || 24)).toFixed(1)} s`;
  }

  function drawShot(entry, opts) {
    const r = entry.recipe;
    if (entry.status === "loading" && !r) return `<p class="note hood-loading">Reading what this shot was rendered with…</p>`;
    if (!r) return `<p class="note hood-error">${esc(entry.error || "Under the hood could not read this shot.")}</p>`;
    const off = !r.rerender.ok || r.kind !== "morph" || r.plays != null;
    const dis = off ? " disabled" : "";
    const ch = r.choices || {};
    const u = r.used || {};
    const fps = Number(ch.fps) || 24;
    const head = [];
    if (r.note) head.push(esc(r.note));
    if (r.verified === true) head.push(`<span class="hood-ok">The clip's own graph matches this record.</span>`);
    if (r.verified === false) head.push(`<span class="hood-bad">The clip's own graph differs from this record.</span>`);
    if (r.plays != null) head.push(`This slot plays shot ${r.plays + 1}'s morph (Move or Duplicate on the Shot tab). <button type="button" class="text" data-hood="select" data-index="${r.plays}">Open shot ${r.plays + 1}</button>`);
    const engine = `${esc(r.engine_label || r.engine || "")}${u.model ? ` · <span class="mono">${esc(u.model)}</span>` : ""}${u.fallback ? " · a Draft morph standing in for the cut's model" : ""}${u.finish ? ` · ${esc(u.finish)}` : ""}`;
    const prompt = String(current(entry, "prompt") || "");
    const negative = String(current(entry, "negative") == null ? "" : current(entry, "negative"));
    const seed = current(entry, "seed");
    const frames = Number(current(entry, "frames") || 0);
    const shotSecs = Number(r.seconds || 0);
    const comp = current(entry, "compression") || [null, null];
    const lora = current(entry, "lora");
    const loras = ch.loras || [];
    const frameOpts = (ch.frames || []).map((n) => `<option value="${n}"${n === frames ? " selected" : ""}>${esc(framesLabel(n, fps))}</option>`).join("");
    const styleOpts = (ch.styles || []).map((s) => `<option value="${esc(s.id)}"${s.id === current(entry, "style") ? " selected" : ""}>${esc(s.label)}</option>`).join("");
    const loraOpts = [`<option value=""${!lora ? " selected" : ""}>none</option>`].concat(
      loras.concat(lora && lora.name && !loras.includes(lora.name) ? [lora.name] : []).map((n) => `<option value="${esc(n)}"${lora && lora.name === n ? " selected" : ""}>${esc(n)}</option>`)).join("");
    const presetSeed = presetOf(entry, "seed");
    const rows = [
      row(entry, "model", "Model", `<span class="hood-text" id="%ID%">${engine || "not recorded"}</span>`),
      row(entry, "prompt", "Prompt", `<textarea id="%ID%" rows="3" data-hood-in="prompt" spellcheck="false"${dis}>${esc(prompt)}</textarea>`,
        mark(entry, "prompt").differs ? `<details class="hood-preset"><summary>preset words</summary><p>${esc(presetOf(entry, "prompt") || "")}</p></details>` : ""),
      row(entry, "negative", "Negative", `<textarea id="%ID%" rows="2" data-hood-in="negative" spellcheck="false"${dis}>${esc(negative)}</textarea>`,
        ghost(entry, "negative", presetOf(entry, "negative") || "")),
      row(entry, "", "From still", `<span class="hood-text" id="%ID%">${stillName(u.from) || "?"}</span>`),
      row(entry, "", "To still", `<span class="hood-text" id="%ID%">${stillName(u.to) || "?"}</span>`),
      row(entry, "seed", "Seed", `<input type="number" id="%ID%" min="0" step="1" data-hood-in="seed" value="${seed == null ? "" : esc(seed)}"${dis} />
          <button type="button" class="text" data-hood="seed-next"${dis} title="The next seed in this shot's own sequence">next (${esc(r.next_seed == null ? "" : r.next_seed)})</button>
          <button type="button" class="text" data-hood="seed-dice"${dis} title="Any seed">dice</button>`,
        presetSeed != null ? `<span class="hood-preset${mark(entry, "seed").differs ? "" : " quiet"}">preset: ${esc(presetSeed)}${entry.preset && entry.preset.seed_rule ? ` (${esc(entry.preset.seed_rule)})` : ""}</span>` : ""),
      row(entry, "steps", "Steps", `<input type="number" id="%ID%" min="${(ch.steps || [1])[0]}" max="${(ch.steps || [1, 100])[1]}" step="1" data-hood-in="steps" value="${esc(current(entry, "steps") == null ? "" : current(entry, "steps"))}"${dis} />`,
        ghost(entry, "steps", presetOf(entry, "steps"))),
      row(entry, "cfg", "CFG", `<input type="number" id="%ID%" min="${(ch.cfg || [1])[0]}" max="${(ch.cfg || [1, 20])[1]}" step="0.1" data-hood-in="cfg" value="${esc(current(entry, "cfg") == null ? "" : current(entry, "cfg"))}"${dis} />`,
        ghost(entry, "cfg", presetOf(entry, "cfg"))),
      row(entry, "frames", "Frames", `<select id="%ID%" data-hood-in="frames"${dis}>${frameOpts}</select>`,
        `<span class="hood-sub">${frames ? `the shot plays ${shotSecs.toFixed(1)} s of it` : ""}</span>${ghost(entry, "frames", framesLabel(presetOf(entry, "frames"), fps))}`),
      row(entry, "", "Size", `<span class="hood-text" id="%ID%">${u.width && u.height ? `${u.width} × ${u.height}` : "?"}${u.out ? ` · out ${esc(u.out[0])} × ${esc(u.out[1])}` : ""}${u.upscaler ? ` · ${esc(u.upscaler)}` : ""}</span>`),
      row(entry, "guide_start", "First guide", `<input type="number" id="%ID%" min="0" max="1" step="0.05" data-hood-in="guide_start" value="${esc(current(entry, "guide_start") == null ? "" : current(entry, "guide_start"))}"${dis} />`,
        ghost(entry, "guide_start", presetOf(entry, "guide_start"))),
      row(entry, "guide_end", "Last guide", `<input type="number" id="%ID%" min="0" max="1" step="0.05" data-hood-in="guide_end" value="${esc(current(entry, "guide_end") == null ? "" : current(entry, "guide_end"))}"${dis} />`,
        ghost(entry, "guide_end", presetOf(entry, "guide_end"))),
      row(entry, "compression", "Compression", `<input type="number" id="%ID%" min="0" max="100" step="1" data-hood-in="compression" data-end="0" value="${esc(comp[0] == null ? "" : comp[0])}" aria-label="Start still's compression"${dis} />
          <input type="number" min="0" max="100" step="1" data-hood-in="compression" data-end="1" value="${esc(comp[1] == null ? "" : comp[1])}" aria-label="End still's compression"${dis} />`,
        ghost(entry, "compression", (presetOf(entry, "compression") || []).join(" · "))),
      row(entry, "style", "Morph style", `<select id="%ID%" data-hood-in="style"${dis}>${styleOpts}</select>`,
        `<span class="hood-sub">${esc(((ch.styles || []).find((s) => s.id === current(entry, "style")) || {}).note || "")}</span>`),
      row(entry, "lora", "LoRA", `<select id="%ID%" data-hood-in="lora"${dis}${!loras.length && !lora ? " title=\"No LoRA files in this machine's loras folder\"" : ""}>${loraOpts}</select>
          ${lora ? `<input type="number" min="-2" max="2" step="0.05" data-hood-in="lora_strength" value="${esc(lora.strength == null ? 1 : lora.strength)}" aria-label="LoRA strength"${dis} />` : ""}`,
        `<span class="hood-sub">${loras.length ? "the Draft graph takes one only when you pick it" : "none in this machine's loras folder"}</span>`),
    ].join("");
    const cost = r.cost || {};
    const waiting = pending(entry);
    const job = running.get(String(opts.jobId));
    const mine = job && Number(job.shot) === Number(opts.shotIndex);
    const other = job && !mine;
    const nextSeed = r.next_seed;
    const what = waiting.length ? `${waiting.length} change${waiting.length === 1 ? "" : "s"}: rendered with seed ${esc(current(entry, "seed"))}` : `Nothing changed: another take with the next seed${nextSeed != null ? ` (${esc(nextSeed)})` : ""}`;
    const progress = mine ? `<div class="hood-progress" role="status"><span class="hood-bar"><i style="width:${Math.round(100 * Math.max(0.03, Math.min(1, Number(job.progress) || 0)))}%"></i></span>
        <span class="note">${esc(job.detail || "Re-rendering this shot on the GPU")} · the timeline stays usable</span></div>` : "";
    const actions = mine ? progress : `<div class="hood-actions">
        <button type="button" class="generate" data-hood="rerender"${off || other ? " disabled" : ""}>Re-render this shot</button>
        <button type="button" class="ghost" data-hood="copy">Copy recipe</button>
        <button type="button" class="ghost" data-hood="reset"${off ? " disabled" : ""}>Reset to preset</button>
      </div>
      <p class="note hood-cost"><b class="hood-tag gpu">GPU</b> 1 morph, ${esc(secs(cost.gpu_s))} on this GPU, then ${esc(secs(cost.recut_s))} to re-cut (no GPU)${cost.basis ? ` · ${esc(cost.basis)}` : ""}.${off ? "" : ` <span class="hood-what">${esc(what)}.</span>`}</p>
      ${other ? `<p class="note">An edit is running on shot ${Number(job.shot) + 1}: Re-render waits for it.</p>` : ""}`;
    const why = !r.rerender.ok ? `<p class="note hood-why">${esc(r.rerender.why)}</p>` : "";
    const takes = (r.takes || []).length > 1 || (r.takes || []).some((t) => !t.current) ? `<div class="hood-takes"><span class="hood-label">Takes</span><div class="hood-take-list">${(r.takes || []).slice().reverse().map((t) => {
      const bits = [`#${t.n}`, t.seed != null ? `seed ${t.seed}` : "", t.source === "make" ? "the Make's" : t.source === "swap" ? "after a swap" : "",
        t.overrides && Object.keys(t.overrides).filter((k) => k !== "seed").length ? Object.keys(t.overrides).filter((k) => k !== "seed").join(", ") : ""].filter(Boolean).join(" · ");
      const play = t.url ? ` <a class="hood-link" href="${esc(media(t.url))}" target="_blank" rel="noopener">see it</a>` : "";
      return `<span class="hood-take${t.current ? " current" : ""}">${esc(bits)}${t.current ? " · this one" : t.usable ? ` <button type="button" class="text" data-hood="take" data-n="${t.n}"${job ? " disabled" : ""}>use</button>` : ` <small title="${esc(t.why || "")}">(${esc(t.why || "cannot come back")})</small>`}${play}</span>`;
    }).join("")}</div><span class="note hood-take-cost"><b class="hood-tag">no GPU</b> a take comes back with a re-cut</span></div>` : "";
    const wf = r.source !== "none" && r.workflow ? `<a class="hood-link" href="${esc(media(r.workflow))}" download="${esc(r.workflow_name || "workflow.json")}" data-hood="download">Open in ComfyUI</a>
        <span class="note">downloads the graph this shot ran: drop it on ComfyUI</span>
        ${entry.confirm ? `<span class="hood-confirm" role="group" aria-label="Queue on ComfyUI">Queue it on ComfyUI at ${esc(r.comfy || "this machine")}? It spends ${esc(secs(cost.gpu_s))} of its GPU and the clip lands in ComfyUI's output folder, not in this cut.
            <button type="button" class="ghost" data-hood="queue-yes">Queue it</button><button type="button" class="text" data-hood="queue-no">Cancel</button></span>`
        : `<button type="button" class="text" data-hood="queue">or queue it there…</button>`}` : `<span class="note">Open in ComfyUI: this shot's graph was not kept.</span>`;
    return `<div class="hood-shot">
        ${head.length ? `<p class="note hood-source">${head.join(" ")}</p>` : ""}
        <div class="hood-rows">${rows}</div>
        ${why}
        ${actions}
        ${takes}
        <div class="hood-comfy">${wf}</div>
        ${entry.note ? `<p class="note hood-note" role="status">${esc(entry.note)}</p>` : ""}
      </div>`;
  }

  // ------------------------------------------------------------------------------------------ the project scope

  function drawProject(opts) {
    const got = (typeof opts.project === "function" ? opts.project() : opts.project) || {};
    const rows = (got.rows || []).map((r) => {
      const value = r.choices && r.choices.length
        ? `<div class="toggle chips" role="group" aria-label="${esc(r.label)}">${r.choices.map((c) => `<button type="button" class="chip${c.on ? " on" : ""}" data-act="${esc(r.act || "")}" data-value="${esc(c.value)}" aria-pressed="${c.on ? "true" : "false"}"${r.disabled ? " disabled" : ""}>${esc(c.label)}</button>`).join("")}</div>`
        : `<span class="hood-text${r.copy ? " hood-code" : ""}">${esc(r.value == null ? "" : r.value)}</span>`;
      const link = r.link ? (r.link.href ? ` <a class="hood-link" href="${esc(r.link.href)}"${r.link.newTab ? " target=\"_blank\" rel=\"noopener\"" : ""}>${esc(r.link.label)}</a>`
        : ` <button type="button" class="text" data-act="${esc(r.link.act || "")}"${r.link.hash ? ` data-hash="${esc(r.link.hash)}"` : ""}${r.link.id ? ` data-id="${esc(r.link.id)}"` : ""}>${esc(r.link.label)}</button>`) : "";
      const copy = r.copy ? ` <button type="button" class="text" data-hood="copy-text" data-text="${esc(r.copy)}">Copy</button>` : "";
      return `<div class="hood-row" tabindex="${r.choices && r.choices.length ? "-1" : "0"}" data-hood-row="${esc(r.key || "")}">
          <span class="hood-label">${esc(r.label)}</span>
          <div class="hood-value">${value}${link}${copy}</div>
          <span class="hood-tags">${r.where ? `<i class="hood-where">${esc(r.where)}</i>` : ""}${r.cost ? `<i class="hood-tag${/gpu|credit/i.test(r.cost) ? " gpu" : ""}">${esc(r.cost)}</i>` : ""}</span>
          ${r.hint ? `<p class="hood-hint">${esc(r.hint)}</p>` : ""}
        </div>`;
    }).join("");
    return `<div class="hood-project">${got.note ? `<p class="note hood-source">${esc(got.note)}</p>` : ""}<div class="hood-rows">${rows}</div></div>`;
  }

  // ------------------------------------------------------------------------------------------ mounting

  let uid = 0;
  function redraw(entry) {
    (entry.hosts || []).forEach((host) => {
      if (!host.isConnected || !host.__hood) return;
      draw(host, host.__hood.opts);
    });
  }
  function draw(host, opts) {
    if (opts.shotIndex == null) {
      host.innerHTML = drawProject(opts);
      return;
    }
    const entry = cache.get(keyOf(opts));
    const focus = document.activeElement && host.contains(document.activeElement) ? document.activeElement.getAttribute("data-hood-in") : null;
    host.innerHTML = drawShot(entry, opts);
    if (focus) {
      const again = host.querySelector(`[data-hood-in="${focus}"]`);
      if (again) again.focus();
    }
  }

  function mount(host, opts) {
    if (!host) return null;
    opts = Object.assign({ shotIndex: null }, opts || {});
    if (opts.shotIndex == null && !opts.project) return { refresh: () => null };  // a host that draws its own rows keeps them
    host.classList.add("hood");
    host.__hood = { opts };
    if (opts.shotIndex == null) {
      draw(host, opts);
      return { refresh: () => draw(host, opts) };
    }
    const key = keyOf(opts);
    let entry = cache.get(key);
    if (!entry) {
      uid += 1;
      entry = { uid, recipe: null, preset: null, edits: {}, follow: true, status: "loading", note: "", hosts: [] };
      cache.set(key, entry);
      load(entry, opts);
    }
    entry.hosts = (entry.hosts || []).filter((h) => h.isConnected && h !== host).concat([host]);
    if (!host.__hoodBound) {
      host.__hoodBound = true;
      host.addEventListener("click", (event) => onClick(host, event));
      host.addEventListener("input", (event) => onInput(host, event));
      host.addEventListener("change", (event) => onInput(host, event, true));
    }
    draw(host, opts);
    return { refresh: () => load(entry, opts) };
  }

  function entryOf(host) {
    const opts = host.__hood && host.__hood.opts;
    return opts ? [cache.get(keyOf(opts)), opts] : [null, null];
  }

  function onInput(host, event, committed) {
    const el = event.target.closest("[data-hood-in]");
    if (!el) return;
    const [entry, opts] = entryOf(host);
    if (!entry || !entry.recipe) return;
    const k = el.getAttribute("data-hood-in");
    const raw = el.value;
    if (k === "compression") {
      const both = (current(entry, "compression") || [0, 0]).slice();
      both[Number(el.dataset.end || 0)] = raw === "" ? null : Number(raw);
      entry.edits.compression = both;
    } else if (k === "lora") {
      entry.edits.lora = raw ? { name: raw, strength: Number((current(entry, "lora") || {}).strength || 1) } : null;
    } else if (k === "lora_strength") {
      const l = current(entry, "lora");
      if (l) entry.edits.lora = { name: l.name, strength: Number(raw) };
    } else if (k === "prompt" || k === "negative") {
      entry.edits[k] = raw;
      if (k === "prompt") entry.follow = false;  // the words are yours now: a style change leaves them alone
    } else if (k === "style") {
      entry.edits.style = raw;
      load(entry, opts, raw);  // the preset for that style: its prompt follows unless you wrote your own
    } else {
      entry.edits[k] = raw === "" ? null : Number(raw);
    }
    if (committed || k === "lora" || k === "style") redraw(entry);
    else paintMarks(host, entry);
  }

  // while typing, only the marks and the action line move (the field keeps its caret)
  function paintMarks(host, entry) {
    host.querySelectorAll("[data-hood-row]").forEach((el) => {
      const k = el.getAttribute("data-hood-row");
      if (!k) return;
      const m = mark(entry, k);
      el.classList.toggle("differs", m.differs);
      el.classList.toggle("waiting", m.wait);
      const sign = el.querySelector(".hood-mark");
      if (sign) sign.textContent = m.sign;
    });
    const line = host.querySelector(".hood-what");
    if (line) {
      const waiting = pending(entry);
      const r = entry.recipe || {};
      line.textContent = waiting.length ? `${waiting.length} change${waiting.length === 1 ? "" : "s"}: rendered with seed ${current(entry, "seed")}.`
        : `Nothing changed: another take with the next seed${r.next_seed != null ? ` (${r.next_seed})` : ""}.`;
    }
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      return false;
    }
  }

  async function onClick(host, event) {
    const el = event.target.closest("[data-hood]");
    if (!el || !host.contains(el)) return;
    const act = el.getAttribute("data-hood");
    if (act === "copy-text") {
      const ok = await copy(el.dataset.text || "");
      el.textContent = ok ? "Copied" : "Select it to copy";
      return;
    }
    const [entry, opts] = entryOf(host);
    if (!entry || !entry.recipe) return;
    const r = entry.recipe;
    if (act === "download") return;  // the browser downloads it
    event.preventDefault();
    if (act === "select" && opts.onSelect) {
      opts.onSelect(Number(el.dataset.index));
    } else if (act === "seed-next") {
      entry.edits.seed = Number(r.next_seed);
      redraw(entry);
    } else if (act === "seed-dice") {
      entry.edits.seed = Math.floor(Math.random() * 2147483647);
      redraw(entry);
    } else if (act === "reset") {
      // the preset's values, waiting for Re-render: the Make's own request comes back from the morph cache, no GPU
      const style = r.make_style || used(entry, "style");
      entry.edits = { style, lora: null };
      entry.follow = true;
      if (r.preset && same(style, r.preset.style)) entry.preset = r.preset;  // the shot's own style: its preset is at hand
      else if (!entry.preset || !same(style, entry.preset.style)) await load(entry, opts, style);
      EDITABLE.filter((k) => !["style", "lora", "prompt"].includes(k)).forEach((k) => {
        const p = presetOf(entry, k);
        if (p !== undefined) entry.edits[k] = p;
      });
      entry.note = "The preset's values are in: Re-render to make them the shot's (the Make's own morph comes back from the cache).";
      redraw(entry);
    } else if (act === "copy") {
      const code = r.recipe_code || "";
      const ok = code && (await copy(code));
      entry.note = !code ? "This cut has no recipe code to copy." : ok ? (r.recipe_shot ? "Recipe copied: the cut's code with this shot's own values in it." : "Recipe copied: this shot has no values of its own, so it is the cut's code.") : `Recipe: ${code}`;
      redraw(entry);
    } else if (act === "queue") {
      entry.confirm = true;
      redraw(entry);
    } else if (act === "queue-no") {
      entry.confirm = false;
      redraw(entry);
    } else if (act === "queue-yes") {
      entry.confirm = false;
      entry.note = "Queueing on ComfyUI…";
      redraw(entry);
      try {
        const res = await api(`/api/jobs/${encodeURIComponent(opts.jobId)}/shots/${Number(opts.shotIndex)}/comfy`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true, layer: opts.layer || undefined }) });
        const data = await res.json().catch(() => ({}));
        entry.note = res.ok ? data.note || "Queued on ComfyUI." : data.detail || "ComfyUI did not take it.";
      } catch (err) {
        entry.note = "ComfyUI did not answer.";
      }
      redraw(entry);
    } else if (act === "rerender") {
      const { body, changed } = bodyOf(entry, opts);
      const info = { changed, label: changed.length ? `Re-rendering shot ${Number(opts.shotIndex) + 1} with ${changed.length} change${changed.length === 1 ? "" : "s"}` : `Re-rendering shot ${Number(opts.shotIndex) + 1}: another take` };
      entry.note = "";
      const started = opts.onRerender ? await opts.onRerender(body, info) : await postEdit(opts, "rerender", body, info.label);
      if (started !== true) {  // the host's answer is true, or the reason it did not start
        entry.note = typeof started === "string" && started ? started : entry.note || "That did not start.";
        redraw(entry);
      }
    } else if (act === "take") {
      const n = Number(el.dataset.n);
      const info = { label: `Putting take ${n} back on shot ${Number(opts.shotIndex) + 1} (no GPU, a re-cut)` };
      const started = opts.onTake ? await opts.onTake(n, info) : await postEdit(opts, `shots/${Number(opts.shotIndex)}/take`, { n, layer: opts.layer || undefined }, info.label);
      if (started !== true) {
        entry.note = typeof started === "string" && started ? started : entry.note || "That take did not come back.";
        redraw(entry);
      }
    }
  }

  // with no host to start it (the panel docked on its own), the edit is posted and followed here
  async function postEdit(opts, route, body, label) {
    const id = String(opts.jobId);
    const res = await api(`/api/jobs/${encodeURIComponent(id)}/${route}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const entry = cache.get(keyOf(opts));
      if (entry) entry.note = err.detail || "That did not start.";
      return false;
    }
    progress(id, { shot: opts.shotIndex, progress: 0.05, detail: label, status: "running" });
    const follow = async () => {
      const r = await api(`/api/jobs/${encodeURIComponent(id)}`).catch(() => null);
      const job = r && r.ok ? await r.json() : null;
      if (job && job.status === "running") {
        progress(id, { shot: opts.shotIndex, progress: job.progress, detail: job.detail, status: "running" });
        setTimeout(follow, 700);
        return;
      }
      progress(id, null);
      invalidate(id);
      document.dispatchEvent(new CustomEvent("xeno-hood-landed", { detail: { jobId: id, job } }));
      const entry = cache.get(keyOf(opts));
      if (!entry) {
        const host = Array.from(document.querySelectorAll(".hood")).find((h) => h.__hood && keyOf(h.__hood.opts) === keyOf(opts));
        if (host) mount(host, opts);
      }
    };
    setTimeout(follow, 700);
    return true;
  }

  function progress(jobId, info) {
    const id = String(jobId);
    if (info && info.status !== "done") running.set(id, info);
    else running.delete(id);
    cache.forEach((entry, key) => {
      if (key.split("|")[0] !== id) return;
      (entry.hosts || []).forEach((host) => {
        if (!host.isConnected) return;
        const bar = host.querySelector(".hood-progress");
        const mine = info && Number(info.shot) === Number(host.__hood.opts.shotIndex);
        if (bar && mine) {  // patched in place while it runs: the panel keeps its fields
          const fill = bar.querySelector(".hood-bar i");
          if (fill) fill.style.width = `${Math.round(100 * Math.max(0.03, Math.min(1, Number(info.progress) || 0)))}%`;
          const note = bar.querySelector(".note");
          if (note) note.textContent = `${info.detail || "Re-rendering this shot on the GPU"} · the timeline stays usable`;
        } else {
          draw(host, host.__hood.opts);
        }
      });
    });
  }

  function invalidate(jobId) {
    const id = String(jobId);
    Array.from(cache.keys()).forEach((key) => {
      if (key.split("|")[0] === id) cache.delete(key);
    });
  }

  window.XenoHood = { mount, progress, invalidate, version: 1,
    // the pure parts, for the tests (tests/test_hood_desk.py runs them under node)
    _values: { bodyOf, pending, current, used, presetOf, same } };
})();
