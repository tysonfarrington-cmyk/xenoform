const SLIDERS = [
  ["kick", "Kick", "morph impulse"],
  ["bass", "Bass", "camera push"],
  ["hats", "Hats", "flicker"],
  ["vocals", "Vocals", "surface"],
  ["liquidity", "Liquidity", "how wet the body stays"],
  ["chaos", "Chaos", "how far a drop may go"],
  ["material", "Material", "chrome against flesh"],
  ["camera", "Camera energy", "orbit and push"],
];

const LOCK_ROWS = [
  ["register", "Register"],
  ...SLIDERS.map(([key, name]) => [key, name]),
  ["quality", "Quality"],
  ["preset", "Look"],
  ["script", "Script"],
];

let state = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function api(path, options) {
  const base = window.XENO_BASE || "";
  const full = /^https?:/.test(path) ? path : base + path;
  return window.fetch(full, options);
}

function media(path) {
  if (!path) return "";
  const base = window.XENO_BASE || "";
  if (/^https?:/.test(path)) return path;
  if (base && path.startsWith("/") && !path.startsWith(base + "/")) return base + path;
  return path;
}

const SAMPLE_NOTE = "the ending plops, make it a big splash";

function viewFromHash() {
  const name = (location.hash || "#simple").replace("#", "").split("/")[0];
  if (name === "scene") return "scene";
  if (name === "notes") return "notes";
  if (name === "setup") return "setup";
  if (name === "connect") return "connect";
  if (["director", "script", "looks", "desk"].includes(name)) return "director";
  return "simple";
}

function allForms() {
  return state.forms.concat(state.customs);
}

function formById(id) {
  return allForms().find((form) => form.id === id) || state.forms[0];
}

function layoutBlocks() {
  const duration = Math.max(state.duration || 1, 0.001);
  const cleaned = state.blocks.map((block) => ({
    ...block,
    hold: Math.max(0.2, Math.min(25.5, Number(block.hold) || 1)),
  }));
  const total = cleaned.reduce((sum, block) => sum + block.hold, 0) || 1;
  let cursor = 0;
  return cleaned.map((block) => {
    const span = (duration * block.hold) / total;
    const row = { ...block, start: cursor, end: cursor + span };
    cursor += span;
    return row;
  });
}

function clock(seconds) {
  const safe = Math.max(0, seconds);
  const m = Math.floor(safe / 60);
  const s = Math.floor(safe % 60);
  const tenth = Math.floor((safe % 1) * 10);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${tenth}`;
}

function lookName() {
  const preset = state.presets.find((item) => item.id === state.preset);
  return preset ? preset.name : "Custom";
}

function paintRegisters() {
  const slot = document.getElementById("register-slot");
  if (!slot || !state || !state.registers) return;
  const register = activeRegister();
  if (register) {
    document.documentElement.style.setProperty("--accent", register.accent);
    document.body.dataset.register = register.id;
  }
  const buttons = state.registers
    .map((item) => {
      const on = item.id === state.register ? " on" : "";
      return `<button type="button" class="register-btn${on}" data-act="register" data-register="${esc(item.id)}" style="border-top-color:${esc(item.accent)}">
        <strong>${esc(item.name)}</strong>
        <span>${esc(item.voice)}</span>
      </button>`;
    })
    .join("");
  const cards = (state.cards || [])
    .map(
      (card) => `<label>${card.at === "drop" ? "Drop card" : "Outro card"}
        <input data-card="${esc(card.at)}" type="text" maxlength="80" value="${esc(card.text)}" placeholder="${card.at === "drop" ? "A line for the drop" : "A line for the outro"}" aria-label="${card.at === "drop" ? "Drop card" : "Outro card"}" />
      </label>`,
    )
    .join("");
  slot.innerHTML = `<section class="register-band" aria-label="Register">
    <div class="register-top">
      <div>
        <p class="kicker">Register</p>
        <h2>${esc(registerName())}</h2>
      </div>
      <p class="voice">${esc(register ? register.voice : "")}</p>
      ${lockButton("register", "register")}
    </div>
    <div class="register-row">${buttons}</div>
    <div class="card-row">${cards}</div>
  </section>`;
}

function customScript() {
  if (!state.customs.length) {
    return [{ form: "", hold: Math.max(0.2, state.duration || 1), transition: "ribbon", energy: "calm" }];
  }
  const sections = state.sections.length ? state.sections : [{ label: "calm", start: 0, end: state.duration || 1 }];
  return sections.map((section, index) => {
    const last = index === sections.length - 1;
    const energy = section.label === "drop" ? "drop" : last ? "outro" : section.label;
    const transition = energy === "drop" ? "ribbon" : energy === "outro" ? "pour-harden" : "ribbon";
    return {
      form: state.customs[index % state.customs.length].id,
      hold: Math.round((section.end - section.start) * 100) / 100,
      transition,
      energy,
    };
  });
}

function applyRegister(id, respectLocks) {
  const register = state.registers.find((item) => item.id === id);
  if (!register) return;
  if (respectLocks && state.locks.register) return;
  state.register = register.id;
  state.palette = register.palette;
  state.flash = register.flash;
  state.preset = "";
  for (const key of Object.keys(register.sliders)) {
    if (!respectLocks || !state.locks[key]) state.sliders[key] = register.sliders[key];
  }
  state.cards = register.cards.map((card) => ({ at: card.at, text: card.text }));
  document.documentElement.style.setProperty("--accent", register.accent);
  if (!respectLocks || !state.locks.script) {
    state.motif = "";
    planStory({ scenes: [] });
  }
}

function payload() {
  return {
    audio_id: state.audioId,
    preset: state.preset || "",
    quality: state.quality,
    register: state.register || "",
    palette: state.palette || "neutral",
    flash: state.flash || "normal",
    cards: (state.cards || []).map((card) => ({ at: card.at, text: card.text || "" })),
    sliders: state.sliders,
    locks: state.locks,
    blocks: state.blocks.map((block) => ({
      form: block.form,
      hold: Number(block.hold),
      transition: block.transition,
      energy: block.energy || "",
    })),
    customs: state.customs.map((form) => ({
      id: form.id,
      noun: form.noun || form.name,
      name: form.name,
      kind: form.kind || "noun",
    })),
    live: state.live,
    morph_hit: state.morphHit !== false,
    endpoint: state.endpoint,
    addons: !!state.addons,
    library_folder: state.libraryFolder || "",
    exclude_faces: state.excludeFaces !== false,
    allow_pd_us: !!state.allowPdUs,
    library_pins: state.libraryPins || [],
    library_bans: state.libraryBans || [],
    vibe: (state.easy && state.easy.vibe) || "",
    // Cloud quality: optional, paid, off by default. Only the confirm click sets the token.
    paid_cloud: !!state.paidCloud,
    // Guardrails: open-weights (contest) mode unless paid cloud is switched on; Expert keeps values, warns only.
    open_weights_only: !state.paidCloud,
    expert: localStorage.getItem("xeno-guard-expert") === "1",
    cloud_quality: !!(state.paidCloud && state.easy && state.easy.cloud && state.easy.cloudToken),
    cloud_confirm: (state.easy && state.easy.cloud && state.easy.cloudToken) || "",
    beat_overlay: !!(state.easy && state.easy.overlay),
    // Simple finishing (open weights): energy preset, aspect, quality tier, beat FX, end card.
    energy_preset: (state.easy && state.easy.energyPreset) || "dense",
    aspect: (state.easy && state.easy.aspect) || "9:16",
    quality_tier: (state.easy && state.easy.tier) || "draft",
    vertical_mode: (state.easy && state.easy.vertical) || "auto",
    morph_count: (state.easy && state.easy.morphs) || "auto",
    beat_fx: !(state.easy && state.easy.fx === false),
    end_card: !!(state.easy && state.easy.endCard),
    // The house look (demo_house): dance_fx "auto" | "off" | a preset; stem_orbit on unless switched off.
    dance_fx: (state.easy && state.easy.danceFx) || "auto",
    stem_orbit: !(state.easy && state.easy.stemOrbit === false),
    macros: (window.XENO_MACROS ? window.XENO_MACROS() : null),
    length_s: Number((state.easy && state.easy.lengthS) || 0),
    hardware_tier: (state.easy && state.easy.gpuTier) || "auto",
    performer: Number((state.easy && state.easy.performer) || 0),
    performer_style: (state.easy && state.easy.performerStyle) || "auto",
    // Your own clips and images (Simple): a folder on this machine, or the files dropped on the desk (own_id)
    own_folder: (state.easy && state.easy.ownFolder) || "",
    own_id: (state.easy && state.easy.ownId) || "",
    // Advanced desk: one scene transition per boundary (guardrails keep each type to 2; overflow becomes a cut).
    scene_transitions: sceneTransitionPlan().map((row) => ({ kind: row.kind, boundary: row.boundary, index: row.index, auto: row.auto })),
    idea: (state.easy && state.easy.idea) || "",
    song: (state.easy && state.easy.songLabel) || "",
    cut_plan: (state.easy && (state.easy.cloud || state.easy.remixPlan) && (state.easy.cutPlan || state.easy.remixPlan)) || null,
    video_model: state.videoModel || "ltx-23",
    brief: state.brief || "",
    mode: state.view === "simple" ? "simple" : "director",
    scenes: (state.scenes || []).map((scene) => ({
      index: scene.index,
      start: scene.start,
      end: scene.end,
      seconds: scene.seconds,
      bars: scene.bars,
      bar_seconds: scene.bar_seconds,
      hold: scene.hold,
      beat: scene.beat,
      form: scene.form,
      action: scene.action,
      shot: scene.shot,
      move: scene.move,
      edit: scene.edit,
      mood: scene.mood,
      motif: !!scene.motif,
      edited: !!scene.edited,
      verb: scene.verb || "",
      protagonist: scene.protagonist || "",
      goal: scene.goal || "",
      payoff: scene.payoff || "",
      signature: !!scene.signature,
      conditioning: scene.conditioning || (scene.signature ? "signature" : "first-frame"),
      guide: scene.guide || "",
      retime: scene.retime || null,
      guide_strengths: scene.guide_strengths || null,
      hero_image: scene.hero_image || "",
      chain_from: scene.chain_from == null ? null : scene.chain_from,
      guide_from: scene.guide_from || "",
      prompt: scene.prompt || "",
      lead: scene.lead || "",
      lines: scene.lines || [],
      lock_words: scene.lock_words || [],
      element_ids: scene.element_ids || [],
      because: scene.because || "",
      // Per-shot Look override (a dance_fx preset, "" = the video's Look) and the transition into the next shot.
      dance_fx: scene.dance_fx || "",
      transition: (sceneTransitionPlan()[scene.index] || {}).kind || "",
      still_name: scene.still_name || "",
      reference_url: scene.reference_url || "",
    })),
    only_scenes: state.textOnly ? state.onlyScenes || [] : [],
    energy: Number(state.energy || 0),
    continuous: !!state.continuous,
    hero_id: state.heroId || "",
    title_card: state.titleText || "",
    end_card: state.endText || "",
    motif: state.motif || "",
    callback: state.callback || "",
    climax: state.climax == null ? null : state.climax,
    treatment: state.treatment || "",
    guide_id: state.guideId || "",
    interpolate: !!state.interpolate,
  };
}

function lockButton(key, label) {
  const on = state.locks[key] ? " on" : "";
  const pressed = state.locks[key] ? "true" : "false";
  return `<button type="button" class="lock${on}" data-act="lock" data-key="${esc(key)}" aria-pressed="${pressed}" aria-label="Lock ${esc(label)}">
    <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4">
      <rect x="3" y="6" width="8" height="6"/>
      <path d="M5 6V4.2a2 2 0 0 1 4 0V6"/>
    </svg>
  </button>`;
}

function sliderRow(key, name, hint) {
  const value = Number(state.sliders[key] ?? 0.5);
  return `<div class="slider">
    <div class="name">${esc(name)}<small>${esc(hint)}</small></div>
    <span class="val">${Math.round(value * 100)}</span>
    ${lockButton(key, name)}
    <input type="range" min="0" max="1" step="0.01" value="${value}" data-slider="${esc(key)}" aria-label="${esc(name)}" />
  </div>`;
}

const FALLBACK_ETA = {
  live: { label: "Live", short: "now", line: "The picture is in the browser. Record writes an mp4 with no model." },
  turbo: { label: "Turbo", short: "~1 min", line: "Animatic in about 5 seconds, then the GPU morph pass for a 12-20 s song on a 12 GB GPU: about 1 minute on a first run with the GPU idle, about 2 minutes if ComfyUI just had another model loaded, and 45-65 s warm. A live countdown follows the real pace." },
  draft: { label: "Draft", short: "~4 min", line: "512×288. About 4 minutes the first time on a 12 GB GPU." },
  final: { label: "Final", short: "~10 min", line: "640×360 at 24 fps. About 10 minutes on a 12 GB GPU. Same seed as Turbo." },
};

function qualityLabel(value) {
  if (value === "live") return "Live";
  if (value === "turbo") return "Turbo";
  if (value === "final") return "Final";
  return "Draft";
}

function etaFor(id) {
  return (state.etas && state.etas[id]) || FALLBACK_ETA[id] || { label: qualityLabel(id), short: "", line: "" };
}

function qualityToggle() {
  const buttons = ["live", "turbo", "draft", "final"].map((id) => {
    const eta = etaFor(id);
    const on = state.quality === id ? " on" : "";
    return `<button type="button" class="${on}" data-act="quality" data-quality="${id}"><b>${esc(eta.label || qualityLabel(id))}</b><small>${esc(eta.short || "")}</small></button>`;
  }).join("");
  const current = etaFor(state.quality || "live");
  return `<div class="toggle quality" role="group" aria-label="Quality">${buttons}</div><p class="eta">${esc(current.line || "")}</p>`;
}

function stageMedia() {
  if (state.quality === "live") {
    const src = state.audioUrl || "/media/audio/demo";
    const ai = state.liveAiRequested ? " checked" : "";
    return `<div class="live-wrap">
      <canvas id="live-canvas" width="768" height="432" aria-label="Live liquid body"></canvas>
      <audio id="live-audio" src="${esc(media(src))}" preload="auto"></audio>
      <div class="live-bar" data-tour="live">
        <button type="button" class="generate" data-act="live-play">Play</button>
        <button type="button" class="ghost" data-act="live-record">${state.recording ? "Stop" : "Record"}</button>
        <label class="check"><input type="checkbox" data-act="live-ai"${ai} /> Live+AI</label>
        <span id="live-note">Live. Edits land on the next frame.</span>
      </div>
    </div>`;
  }
  const fill = state.interpolate ? " checked" : "";
  const src = state.previewUrl || state.video || "";
  const poster = state.previewUrl ? "" : ` poster="${media("/media/poster")}"`;
  return `<video id="player" controls playsinline${poster} src="${esc(media(src))}"></video>
    <label class="check fill-check"><input type="checkbox" data-act="interpolate"${fill} /> Fill to 24 fps</label>`;
}

function stagesHtml() {
  if (state.quality === "live") {
    return `<p class="note">Live draws in this window. Record writes an mp4 with no model. Turbo, Draft, and Final can use that file as a motion guide.</p>`;
  }
  const turbo = state.quality === "turbo";
  const order = turbo
    ? (state.live
      ? [["analyze", "Analyze"], ["animatic", "Animatic"], ["restyle", "Turbo"], ["assemble", "Lock"]]
      : [["analyze", "Analyze"], ["animatic", "Animatic"], ["assemble", "Lock"]])
    : [
    ["analyze", "Analyze"],
    ["render", "Beauty"],
    ["restyle", "Restyle"],
    ["assemble", "Assemble"],
  ];
  const job = state.job;
  const active = job && job.stage !== "done" ? job.stage : "";
  return `<ol class="stages" id="stages">${order
    .map(([id, label]) => {
      let cls = "";
      let detail = "Waiting";
      let width = 0;
      if (job) {
        const index = order.findIndex((row) => row[0] === id);
        const current = order.findIndex((row) => row[0] === (job.stage === "done" ? "assemble" : job.stage));
        if (job.status === "error" && id === job.stage) cls = "active";
        else if (job.stage === "done" || index < current) {
          cls = "done";
          detail = "Done";
          width = 100;
        } else if (index === current) {
          cls = "active";
          detail = job.detail || "Working";
          width = Math.round((job.progress || 0) * 100);
        }
      } else if (id === "restyle") {
        detail = state.live ? "Live, when you generate" : "Dry run, when you generate";
      }
      return `<li class="${cls}"><b>${label}</b><span>${esc(detail)}<span class="bar"><span style="width:${width}%"></span></span></span></li>`;
    })
    .join("")}</ol>
    <div class="song-actions"><button type="button" class="ghost" data-act="preview" id="preview-btn">Preview</button></div>
    <p class="note" id="preview-note">${esc(state.previewNote || "Low-res animatic. Cut to the beat, before the GPU.")}</p>`;
}

function bandMap() {
  const map = SLIDERS.slice(0, 4).map((row) => sliderRow(...row)).join("");
  const globals = SLIDERS.slice(4).map((row) => sliderRow(...row)).join("");
  return `<section class="panel mix">
      <p class="kicker">Band map</p>
      <h2>What the song does</h2>
      ${map}
      <h3>Globals</h3>
      ${globals}
    </section>`;
}

const RAIL = [
  ["song", "1 Song"],
  ["story", "2 Story"],
  ["cast", "3 Cast lock"],
  ["look", "4 Look"],
  ["shots", "5 Shots"],
  ["morph", "6 Morph"],
  ["notes", "7 Notes & review"],
  ["export", "8 Export"],
];

function railHash(step) {
  if (step === "notes") return "#notes";
  if (step === "setup") return "#setup";
  if (step === "connect") return "#connect";
  if (step === "look" || step === "shots" || step === "morph") return "#director";
  return "#simple";
}

function deskStep() {
  const view = state.view;
  const step = state.step || "song";
  if (view === "notes") return "notes";
  if (view === "setup") return "setup";
  if (view === "connect") return "connect";
  if (view === "scene") return "shots";
  if (view === "director") return ["look", "shots", "morph"].includes(step) ? step : "shots";
  return ["song", "story", "cast", "export"].includes(step) ? step : "song";
}

function goRail(step) {
  state.step = step;
  const hash = railHash(step);
  if ((location.hash || "#simple") === hash) render();
  else location.hash = hash.slice(1);
}

function tourStepFor(target) {
  const map = {
    "[data-tour=song]": "song",
    "[data-tour=beats]": "song",
    "#brief": "story",
    "[data-tour=ideas]": "story",
    "[data-tour=continuity]": "cast",
    "#energy": "cast",
    "[data-tour=gate]": "cast",
    "[data-tour=treatment]": "look",
    "[data-tour=looks]": "look",
    "[data-tour=share]": "export",
  };
  return map[target] || "";
}

function railPills() {
  const bpm = Math.round(Number(state.tempo) || 0);
  const sections = (state.sections || []).length;
  const shots = (state.scenes || []).length;
  const callback = (state.callback || "").trim() ? " · callback set" : "";
  const clips = (state.testClips || []).length;
  const signatures = (state.scenes || []).filter((scene) => scene.signature).length;
  const morphs = signatures || ((state.scenes || []).some((scene) => scene.beat === "climax") ? 1 : 0);
  return {
    song: `${bpm} BPM · ${sections} section${sections === 1 ? "" : "s"}`,
    story: `${shots} shot${shots === 1 ? "" : "s"}${callback}`,
    cast: state.heroUrl ? "Hero locked" : "Hero, prop, place",
    look: registerName(),
    shots: clips >= 1 && clips <= 2 ? `${clips} test clip${clips === 1 ? "" : "s"} approved` : "2 test clips to approve",
    morph: `New · ${morphs} on the drop`,
  };
}

function railHtml(current) {
  const pills = railPills();
  const order = RAIL.map((row) => row[0]);
  const at = order.indexOf(current);
  const steps = RAIL.map(([id, label], index) => {
    const on = id === current ? " on" : "";
    const done = at > index ? " done" : "";
    const pill = pills[id] ? `<span class="pill${id === "morph" ? " new" : ""}">${esc(pills[id])}</span>` : "";
    return `<button type="button" class="rail-step${on}${done}" data-act="rail" data-step="${id}" aria-current="${on ? "step" : "false"}"><i class="dot"></i><span>${label}${pill}</span></button>`;
  }).join("");
  const footOn = (id) => (current === id ? " on" : "");
  return `<nav class="rail" aria-label="Your video">
    <h2>Your video</h2>
    ${steps}
    <div class="rail-foot">
      <button type="button" class="rail-link${footOn("setup")}" data-act="rail" data-step="setup">Setup &amp; models</button>
      <button type="button" class="rail-link${footOn("connect")}" data-act="rail" data-step="connect">Connect an AI</button>
      <a class="rail-link" href="/judges">Judges page</a>
      <button type="button" class="rail-link" data-act="palette">Ctrl K</button>
    </div>
  </nav>`;
}

function songStep() {
  return `<section class="panel song-drop" data-tour="song">
      <p class="kicker">Song</p>
      <h2>Pick or drop a song</h2>
      <div class="meta">
        <span><b>${Number(state.duration || 0).toFixed(1)}s</b> duration</span>
        <span><b>${Math.round(Number(state.tempo) || 0)}</b> bpm</span>
        <span><b>${(state.beats || []).length}</b> beats</span>
        <span><b>${(state.drops || []).length}</b> drops</span>
      </div>
      <div class="song-actions">
        <label class="upload">Drop a song<input id="song-file" type="file" accept="audio/*,.wav,.mp3,.flac,.ogg" aria-label="Drop a song" /></label>
        <button type="button" class="ghost" data-act="use-demo">Use the bundled demo</button>
      </div>
      <p class="note" id="song-note">The desk opens on examples/demo.wav. Drop a file to analyze another track. Nothing here starts a render.</p>
    </section>
    ${timingPanel()}
    <section class="panel guided-tours" id="guided-tours">
      <p class="kicker">Guided tours</p>
      <h2>Short walks through the desk</h2>
      <div id="tour-list"><p class="note">Opening the tours…</p></div>
    </section>`;
}

function storyStep() {
  const lead = (state.scenes || [])[0] || {};
  const spine = lead.protagonist
    ? `<p class="spine"><b>${esc(lead.protagonist)}</b> · ${esc(lead.goal || "")}<br>${esc(lead.payoff || "")}</p>`
    : "";
  return `<section class="panel brief-panel">
      <p class="kicker">Story</p>
      <h2>Tell it the life. It cuts the song.</h2>
      <label class="brief-label" for="brief">One-line brief</label>
      <textarea id="brief" rows="3" maxlength="180" aria-label="One-line brief">${esc(state.brief || "")}</textarea>
      <label class="idea-field">Callback
        <input id="callback" type="text" maxlength="140" value="${esc(state.callback || "")}" placeholder="the sphere returns at the end, changed" aria-label="Callback" />
      </label>
      <p class="note">One line becomes a protagonist, a goal, and a payoff. Each section is an action shot, hard-cut on the bar. A morph is a signature, once, on the drop.</p>
      <div class="simple-actions">
        <button type="button" class="generate" data-act="try-it">Try the demo</button>
        <button type="button" class="ghost" data-act="generate-inline">Generate this brief</button>
        <div class="generate-gate" data-gate="1"></div>
        <button type="button" class="ghost" data-act="to-director">Open the shots</button>
        <button type="button" class="ghost" data-act="music-only">Music only</button>
      </div>
      ${setupBanner()}
      ${spine}
      <ol class="shotlist">${shotRows()}</ol>
    </section>
    <div class="scene-grid">${sceneCards()}</div>`;
}

function lookStep() {
  const presets = (state.presets || [])
    .map((preset) => {
      const on = preset.id === state.preset ? " on" : "";
      return `<button type="button" class="preset${on}" data-act="preset" data-preset="${esc(preset.id)}"><strong>${esc(preset.name)}</strong><span>${esc(preset.note)}</span></button>`;
    })
    .join("");
  return `${treatmentPanel()}
    <section class="panel">
      <div data-tour="looks">
        <div class="looks-head">
          <div>
            <p class="kicker">Looks</p>
            <h2>${esc(lookName())}</h2>
          </div>
          <button type="button" class="generate" data-act="random">Roll the board</button>
        </div>
        <div class="preset-grid">${presets}</div>
      </div>
      <div class="recipe-code" id="recipe-out">${esc(state.recipe || "")}</div>
      <div class="recipe-actions">
        <button type="button" class="ghost" data-act="copy">Copy</button>
        <input id="recipe-in" type="text" spellcheck="false" placeholder="XF-…" aria-label="Paste a recipe" />
        <button type="button" class="ghost" data-act="restore">Restore</button>
      </div>
      <p class="hint" id="recipe-hint"></p>
      <p class="note">The code carries the storyboard: brief, scenes, callback, motif, and the register. ${lockButton("script", "storyboard")}</p>
    </section>
    ${bandMap()}`;
}

function shotsStep() {
  const arc = ["setup", "rising", "climax", "release"]
    .map((beat) => `<span class="${(state.scenes || []).some((scene) => scene.beat === beat) ? "on" : ""}">${beat}</span>`)
    .join("<i></i>");
  return `<section class="panel">
      <div class="board-head">
        <div>
          <p class="kicker">Shots</p>
          <h2>Storyboard</h2>
        </div>
        <p>One card per section. Hard cuts on the bar. Drag the climax onto a card.</p>
      </div>
      <div class="story-tools">
        <div class="climax-chip" draggable="true" id="climax-token" title="Drag onto a scene">Climax</div>
      </div>
      <div class="beat-rail" aria-hidden="true">${arc}</div>
      <div class="scene-grid">${sceneCards()}</div>
    </section>
    ${state.expanded != null ? sceneEditor() : ""}
    ${transitionRows()}
    ${shotReview()}`;
}

function exportStep() {
  return `<section class="panel">
      <p class="kicker">Export</p>
      <h2>Share the cut you already have</h2>
      <p class="note">Share cut exports a 720p H.264 file under 16 MB from the picture you already have. It does not re-render the shots. Every render also writes a shot list and a seed file beside the picture.</p>
      <div class="simple-actions">
        <a class="ghost" id="notes-link" href="${state.job && state.job.id ? "/api/jobs/" + encodeURIComponent(state.job.id) + "/notes" : "#"}">Shot list</a>
        <a class="ghost" id="seed-link" href="${state.job && state.job.id ? "/api/jobs/" + encodeURIComponent(state.job.id) + "/seed" : "#"}">Seed file</a>
        <button type="button" class="ghost" data-act="export-workflow">ComfyUI workflow</button>
      </div>
      <div class="simple-actions">
        <button type="button" class="generate" data-act="share-cut" data-tour="share">Share cut</button>
        <button type="button" class="ghost" data-act="music-only">Music only</button>
      </div>
      <div class="simple-actions">
        <button type="button" class="ghost" id="vj-link" data-act="vj-open" data-href="${esc(vjUrl())}" title="VJ mode plays this song live; stems ride the macros when they have been split">Open in VJ with this song's stems</button>
        <button type="button" class="ghost" data-act="mcp-copy" title="The mcpServers block for Claude Desktop or Cursor">Copy MCP connect line</button>
        <button type="button" class="ghost" data-act="easy-midi" title="MIDI controller mapping (Simple mode's Fine-tune drawer)">MIDI drawer</button>
      </div>
      <div class="recipe-code" id="recipe-out">${esc(state.recipe || "")}</div>
      <div class="recipe-actions">
        <button type="button" class="ghost" data-act="copy">Copy</button>
        <input id="recipe-in" type="text" spellcheck="false" placeholder="XF-…" aria-label="Paste a recipe" />
        <button type="button" class="ghost" data-act="restore">Restore</button>
      </div>
      <p class="hint" id="recipe-hint"></p>
      ${setupBanner()}
    </section>`;
}

function inspectorFor(step) {
  if (step === "song") return songStep();
  if (step === "story") return storyStep();
  if (step === "cast") return cutPanel();
  if (step === "look") return lookStep();
  if (step === "shots") return shotsStep();
  if (step === "morph") return morphPanel();
  if (step === "notes") return `<section class="panel notes-pane">${notesPanel()}</section>`;
  if (step === "export") return exportStep();
  if (step === "setup") return renderSetup();
  if (step === "connect") return renderConnect();
  return songStep();
}

function shotStill(scene) {
  const clip = { wide: "wide", medium: "medium", close: "close", macro: "close", tracking: "medium", reveal: "reveal", overhead: "reveal" }[scene.shot] || "wide";
  return `/static/library/neon-night/${clip}.jpg`;
}

function timelineHtml() {
  const duration = Number(state.duration || 1) || 1;
  const sections = (state.sections || [])
    .map((section) => {
      const width = Math.max(4, ((Number(section.end) - Number(section.start)) / duration) * 100);
      const label = section.label || "section";
      return `<span class="sec sec-${esc(label)}" style="width:${width}%">${esc(label)}</span>`;
    })
    .join("");
  const shots = (state.scenes || [])
    .map((scene, index) => {
      const span = Math.max(0.4, (Number(scene.end) || 0) - (Number(scene.start) || 0)) || Number(scene.bars || 1);
      const peak = scene.beat === "climax" ? `<span class="cx">Climax</span>` : "";
      const on = state.expanded === index ? " on" : "";
      return `<button type="button" class="tl-shot${on}" data-act="expand" data-index="${index}" style="flex:${span} 1 0;background-image:url(${shotStill(scene)})"><em>${String(index + 1).padStart(2, "0")}</em>${peak}</button>`;
    })
    .join("");
  const marks = [0, 0.25, 0.5, 0.75, 1].map((part) => `<span>${clock(duration * part)}</span>`).join("");
  const join = morphJoin();
  const locked = (state.morphReport && state.morphReport.joins && state.morphReport.joins[0]) || null;
  const markTime = locked ? Number(locked.at) : join.scene ? Number(join.scene.start) : null;
  const markAt = markTime == null ? null : Math.max(0, Math.min(100, (markTime / duration) * 100));
  const hitClass = locked && locked.hit ? " tl-hit" : "";
  const marker = markAt == null ? "" : `<i class="tl-mark${hitClass}" style="left:${markAt}%" title="Morph on the downbeat"></i>`;
  const report = state.qa;
  const chips = report
    ? ["Sync", "Motion", "Morphs", "Flash", "Energy"]
        .map((label) => {
          const key = label === "Morphs" ? "morph" : label.toLowerCase();
          const row = report[key] || {};
          return `<span class="tl-qa ${row.pass ? "ok" : "bad"}">${esc(label)} · ${esc(row.detail || (row.pass ? "Pass" : "Fail"))}</span>`;
        })
        .join("")
    : `<span class="tl-qa">Cast lock · one hero, one prop, one place</span>`;
  return `<section class="desk-timeline" aria-label="Timeline">
      <div class="tl-head"><h3>Timeline</h3><span>Cuts snap to the bar.</span></div>
      <div class="tl-ruler">${marks}</div>
      <div class="tl-lane"><span>Sections</span><div class="tl-sections">${sections}</div></div>
      <div class="tl-lane"><span>Score</span>${scoreLane()}</div>
      <div class="tl-lane"><span>Song</span><canvas class="wave" id="wave" width="640" height="36"></canvas></div>
      <div class="tl-lane"><span>Shots</span><div class="tl-shots">${marker}${shots}</div></div>
      <div class="tl-qa-row">${chips}</div>
    </section>`;
}

function renderAdvanced() {
  const step = deskStep();
  state.step = step;
  const monitor = `<div class="desk-monitor">
      <p class="kicker">Picture · ${esc(qualityLabel(state.quality))}</p>
      <h2>${esc(state.quality === "live" ? "Live" : state.videoLabel || "Picture")}</h2>
      ${stageMedia()}
      <p class="caption"><b>${esc(registerName())}</b> · seed 2727 · ${esc(paletteLabel())} · ${state.live ? "Live endpoint armed" : "Dry run is the default"}</p>
      ${qualityToggle()}
      ${stagesHtml()}
    </div>`;
  return `<div class="desk-app">
    ${railHtml(step)}
    <div class="desk-main">
      <div class="desk-upper">
        ${monitor}
        <div class="desk-inspector">${inspectorFor(step)}</div>
      </div>
      ${timelineHtml()}
    </div>
  </div>`;
}

function monogram(noun) {
  const letter = esc((noun || "?").trim().charAt(0).toUpperCase() || "?");
  return `<svg class="mono-mark" viewBox="0 0 80 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect width="80" height="64" fill="#f4f4f5"/><text x="40" y="40" text-anchor="middle" fill="#2e2752" font-family="Space Grotesk, sans-serif" font-size="28">${letter}</text></svg>`;
}

function formThumb(form) {
  if (form.image) return `<img alt="" src="${esc(media(form.image))}" />`;
  if (form.svg) return form.svg;
  return monogram(form.noun || form.name);
}

function activeRegister() {
  return (state.registers || []).find((item) => item.id === state.register) || null;
}

function registerName() {
  const register = activeRegister();
  return register ? register.name : "No register";
}

function paletteLabel() {
  const register = activeRegister();
  return register ? register.palette_label : "";
}

function registerForms() {
  const register = activeRegister();
  if (!register || register.id === "custom") return state.customs.slice();
  return register.forms.map((id) => state.forms.find((form) => form.id === id)).filter(Boolean);
}

function otherForms() {
  const shown = new Set(registerForms().map((form) => form.id));
  return state.forms.concat(state.customs).filter((form) => !shown.has(form.id));
}

function renderScript() {
  const laid = layoutBlocks();
  const register = activeRegister();
  const packName = register ? register.pack : "Forms";
  const cards = registerForms()
    .map((form) => {
      const on = state.blocks[state.selected] && state.blocks[state.selected].form === form.id ? " on" : "";
      return `<button type="button" class="form-card${on}" data-act="assign" data-form="${esc(form.id)}">
        ${formThumb(form)}
        <strong>${esc(form.name)}</strong>
        <span>${esc(form.blurb || "")}</span>
      </button>`;
    })
    .join("");
  const options = allForms()
    .map((form) => `<option value="${esc(form.id)}">${esc(form.name)}</option>`)
    .join("");
  const transitions = state.transitions
    .map((item) => `<option value="${esc(item.id)}">${esc(item.label)}</option>`)
    .join("");
  const blocks = laid
    .map((block, index) => {
      const accent = (formById(block.form) || {}).accent || "#c6a15a";
      return `<article class="block${index === state.selected ? " on" : ""}" data-act="select-block" data-index="${index}" style="flex-grow:${block.hold};border-top-color:${esc(accent)}">
        <div class="when">${clock(block.start)} – ${clock(block.end)}</div>
        <label>Form
          <select data-act="block-form" data-index="${index}" aria-label="Form in block ${index + 1}">${options.replace(
            `value="${esc(block.form)}"`,
            `value="${esc(block.form)}" selected`,
          )}</select>
        </label>
        <label>Hold
          <input data-act="block-hold" data-index="${index}" type="number" min="0.2" max="25.5" step="0.1" value="${Number(block.hold).toFixed(1)}" aria-label="Hold length for block ${index + 1}" />
        </label>
        <label>Into it
          <select data-act="block-transition" data-index="${index}" aria-label="Transition into block ${index + 1}">${transitions.replace(
            `value="${esc(block.transition)}"`,
            `value="${esc(block.transition)}" selected`,
          )}</select>
        </label>
      </article>`;
    })
    .join("");
  return `<div class="script">
    <section class="panel">
      <div class="pack-head">
        <div>
          <p class="kicker">Forms · ${esc(packName)}</p>
          <h2>${register && register.id === "custom" ? "Built from what you add" : esc(registerName())}</h2>
        </div>
        <p>These cards are the subject in the frame. The shot plays the action. Click one to place it on the selected block. Everything here can still be rewritten.</p>
      </div>
      <div class="form-grid">
        ${cards}
        <div class="add-card">
          <strong>Add your own</strong>
          <span>A noun, or a photo. It joins the script.</span>
          <input id="noun" type="text" maxlength="40" placeholder="glass harmonica" aria-label="Noun for a new form" />
          <div class="add-row">
            <button type="button" class="ghost" data-act="add-noun">Add noun</button>
            <label class="upload">Photo<input id="form-file" type="file" accept="image/png,image/jpeg,image/webp" /></label>
          </div>
        </div>
      </div>
      ${
        otherForms().length
          ? `<details class="other-forms"><summary>Other forms</summary><div class="mini-forms">${otherForms()
              .map(
                (form) =>
                  `<button type="button" data-act="assign" data-form="${esc(form.id)}">${esc(form.name)}</button>`,
              )
              .join("")}</div></details>`
          : ""
      }
    </section>
    <section class="panel">
      <div class="board-head">
        <div>
          <p class="kicker">Song-to-form</p>
          <h2>The script</h2>
        </div>
        <p>Each block is a hold. The widths share the song, so changing a hold refits the others. The menu on the block is the transition into that form. ${lockButton("script", "script")} <span class="mono">${state.locks.script ? "script locked" : "script free"}</span></p>
      </div>
      <div class="timeline">${blocks}</div>
    </section>
  </div>`;
}

function renderLooks() {
  const presets = state.presets
    .map((preset) => {
      const on = preset.id === state.preset ? " on" : "";
      return `<button type="button" class="preset${on}" data-act="preset" data-preset="${esc(preset.id)}">
        <strong>${esc(preset.name)}</strong>
        <span>${esc(preset.note)}</span>
        <em>${esc(qualityLabel(preset.quality))}</em>
      </button>`;
    })
    .join("");
  const locks = LOCK_ROWS.map(([key, name]) => {
    const extra = state.sliders[key] !== undefined ? `<span class="mini">${Math.round(state.sliders[key] * 100)}</span>` : "";
    return `<li><span>${esc(name)}</span><span style="display:flex;gap:8px;align-items:center">${extra}${lockButton(key, name)}</span></li>`;
  }).join("");
  return `<div class="looks">
    <section class="panel">
      <div class="looks-head">
        <div>
          <p class="kicker">Looks</p>
          <h2>${esc(lookName())}</h2>
        </div>
        <p>Eight desks already mixed. Picking one writes the unlocked faders. Locked rows stay where you left them.</p>
      </div>
      <div class="preset-grid">${presets}</div>
    </section>
    <section class="side">
      <div class="panel">
        <p class="kicker">Recipe</p>
        <h2>Take it to another desk</h2>
        <div class="recipe-code" id="recipe-out">${esc(state.recipe)}</div>
        <div class="recipe-actions">
          <button type="button" class="ghost" data-act="copy">Copy</button>
          <input id="recipe-in" type="text" spellcheck="false" placeholder="XF-7Q2K-…" aria-label="Paste a recipe" />
          <button type="button" class="ghost" data-act="restore">Restore</button>
        </div>
        <p class="hint" id="recipe-hint"></p>
        <p class="note">The code holds the register, the cards, the faders, the locks, the script, and custom nouns. A photo is not inside the code.</p>
      </div>
      <div class="panel">
        <div class="die">
          <div>
            <p class="kicker">Chance</p>
            <h2>Randomise</h2>
          </div>
          <button type="button" class="generate" data-act="random">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="1" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5" cy="5" r="1" fill="currentColor"/><circle cx="11" cy="5" r="1" fill="currentColor"/><circle cx="8" cy="8" r="1" fill="currentColor"/><circle cx="5" cy="11" r="1" fill="currentColor"/><circle cx="11" cy="11" r="1" fill="currentColor"/></svg>
            Randomise
          </button>
        </div>
        <ul class="locks">${locks}</ul>
        ${qualityToggle()}
      </div>
    </section>
  </div>`;
}

function formName(id) {
  const form = allForms().find((item) => item.id === id);
  return form ? form.name : id || "The liquid";
}

function choiceOptions(values, current) {
  return (values || [])
    .map((value) => `<option value="${esc(value)}"${value === current ? " selected" : ""}>${esc(value)}</option>`)
    .join("");
}

function sceneCards() {
  return (state.scenes || [])
    .map((scene, index) => {
      const on = state.expanded === index ? " on" : "";
      const peak = scene.beat === "climax" ? " climax" : "";
      return `<article class="scene${on}${peak}" data-index="${index}" draggable="false">
        <header>
          <span class="num">${String(index + 1).padStart(2, "0")}</span>
          <span class="beat">${esc(scene.beat)}</span>
          <span class="when">${clock(scene.start)} · ${scene.bars} bar${scene.bars === 1 ? "" : "s"}</span>
        </header>
        <p class="action">${esc(scene.action)}</p>
        <footer>
          <b>${esc(formName(scene.form))}</b>
          <span>${esc(scene.shot)} · ${esc(scene.move)}</span>
          <span>${esc(scene.edit)} · ${esc(scene.mood)}</span>
        </footer>
        <label class="scene-look">Look
          <select data-act="scene-look" data-index="${index}" aria-label="Look for shot ${index + 1}" title="${esc(lookNote(scene.dance_fx || "auto"))}">${lookOptions(scene.dance_fx || "")}</select>
        </label>
        <div class="scene-actions">
          <button type="button" data-act="expand" data-index="${index}">Open</button>
          <button type="button" data-act="motif" data-index="${index}" class="${state.motif === scene.form ? "on" : ""}">Motif</button>
        </div>
      </article>`;
    })
    .join("");
}

function lookOptions(current) {
  return [["", "Video's Look"], ["off", "Off"]].concat(LOOK_PRESETS.map((id) => [id, lookLabel(id)]))
    .map(([id, text]) => `<option value="${esc(id)}"${id === current ? " selected" : ""} title="${esc(lookNote(id || "auto"))}">${esc(text)}</option>`)
    .join("");
}

// ---------------------------------------------------------------- per-boundary scene transitions (Advanced)

const TRANSITION_EXEMPT = ["cut", "scene-morph", "black-hold"]; // never counted against the max-2 rule
const TRANSITION_MAX = 2;
const RECOMMENDED_FALLBACK = { drop: "scene-morph", switch: "match-cut", beat: "cut", silence: "black-hold" };

// GET /api/v1/transitions: the scene transition catalogue (id, label, note, tier) and the per-vibe picks.
async function loadTransitions() {
  try {
    const res = await api("/api/v1/transitions");
    if (!res.ok) return false;
    const body = await res.json();
    state.transitionCatalog = (body.scene_transitions || []).filter((row) => row && row.id);
    state.transitionRecommended = body.scene_recommended || {};
    return true;
  } catch (err) {
    return false;
  }
}

// The kind of boundary between shot i and shot i+1: drop (the climax / a signature morph), switch (a section
// change in the storyboard's sections), silence (a quiet section), else a plain on-beat cut.
function boundaryKind(index) {
  const scenes = state.scenes || [];
  const next = scenes[index + 1];
  if (!next) return "beat";
  if (next.beat === "climax" || next.signature) return "drop";
  const at = Number(next.start || 0);
  const section = (state.sections || []).find((row) => Math.abs(Number(row.start || 0) - at) < 0.3);
  if (section) {
    const label = String(section.label || "").toLowerCase();
    if (/silence|quiet|breakdown|break\b/.test(label)) return "silence";
    if (/drop|chorus/.test(label) && Number(section.level || 0) >= 0.8) return "drop";
    return "switch";
  }
  return "beat";
}

function recommendedTransition(kind) {
  const vibe = (state.easy && state.easy.vibe) || "";
  const table = (state.transitionRecommended && state.transitionRecommended[vibe]) || RECOMMENDED_FALLBACK;
  return table[kind] || RECOMMENDED_FALLBACK[kind] || "cut";
}

// One row per boundary: the user's pick, else the vibe's recommendation for that boundary kind.
function sceneTransitionPlan() {
  if (!state) return [];
  const scenes = state.scenes || [];
  if (scenes.length < 2) return [];
  const picks = state.sceneTransitions || [];
  const rows = [];
  for (let index = 0; index < scenes.length - 1; index += 1) {
    const kind = boundaryKind(index);
    const chosen = picks[index] || "";
    rows.push({ index, boundary: kind, kind: chosen || recommendedTransition(kind), auto: !chosen });
  }
  return rows;
}

function transitionCounts(rows) {
  const counts = {};
  rows.forEach((row) => {
    if (TRANSITION_EXEMPT.includes(row.kind)) return;
    counts[row.kind] = (counts[row.kind] || 0) + 1;
  });
  return counts;
}

function transitionLabel(id) {
  const row = (state.transitionCatalog || []).find((item) => item.id === id);
  return row ? row.label : id;
}

function transitionRows() {
  const rows = sceneTransitionPlan();
  if (!rows.length) return "";
  const expert = localStorage.getItem("xeno-guard-expert") === "1";
  const catalog = (state.transitionCatalog || []).filter((row) => expert || row.tier !== "classic");
  const order = { premium: 0, core: 1, classic: 2 };
  catalog.sort((a, b) => (order[a.tier] == null ? 9 : order[a.tier]) - (order[b.tier] == null ? 9 : order[b.tier]));
  const counts = transitionCounts(rows);
  const over = Object.keys(counts).filter((kind) => counts[kind] > TRANSITION_MAX);
  const options = (current) => {
    const list = catalog.length ? catalog : Object.keys(RECOMMENDED_FALLBACK).map((k) => ({ id: RECOMMENDED_FALLBACK[k], label: RECOMMENDED_FALLBACK[k], tier: "core" }));
    return list
      .map((row) => `<option value="${esc(row.id)}"${row.id === current ? " selected" : ""} title="${esc(row.note || "")}">${esc(row.label)}${row.tier === "premium" ? " · premium" : row.tier === "classic" ? " · classic" : ""}</option>`)
      .join("");
  };
  const lines = rows
    .map((row) => {
      const count = TRANSITION_EXEMPT.includes(row.kind) ? "" : `${counts[row.kind]}/${TRANSITION_MAX}`;
      const bad = counts[row.kind] > TRANSITION_MAX && !TRANSITION_EXEMPT.includes(row.kind);
      return `<div class="tr-row${bad ? " over" : ""}">
        <span class="tr-at">${String(row.index + 1).padStart(2, "0")} → ${String(row.index + 2).padStart(2, "0")}</span>
        <em class="tr-kind">${esc(row.boundary)}</em>
        <select data-act="scene-transition" data-index="${row.index}" aria-label="Transition from shot ${row.index + 1} to ${row.index + 2}">
          <option value=""${row.auto ? " selected" : ""}>Auto · ${esc(transitionLabel(recommendedTransition(row.boundary)))}</option>
          ${options(row.auto ? "" : row.kind)}
        </select>
        <span class="tr-count">${esc(count)}</span>
      </div>`;
    })
    .join("");
  const warn = over.length
    ? `<p class="note warn tr-warn">${esc(over.map((kind) => `${transitionLabel(kind)} ×${counts[kind]}`).join(", "))}: more than ${TRANSITION_MAX} of one type. The guardrail turns the extra into a clean beat cut${expert ? " (Expert: kept, warned)" : ""}.</p>`
    : `<p class="note tr-ok">Max ${TRANSITION_MAX} of any one transition type. Cuts, scene morphs and black holds do not count.</p>`;
  return `<section class="panel tr-panel" id="transitions">
      <div class="board-head">
        <div>
          <p class="kicker">Transitions</p>
          <h2>One per boundary</h2>
        </div>
        <p>Auto follows the vibe's own picks per boundary kind: drop, switch, beat, silence.${expert ? "" : " Classic wipes need Expert."}</p>
      </div>
      <div class="tr-rows">${lines}</div>
      ${warn}
      <button type="button" class="text" data-act="scene-transition-reset">Back to Auto</button>
    </section>`;
}

function vjUrl() {
  const audio = (state && state.audioId) || "demo";
  const params = new URLSearchParams({ track: audio });
  const stems = window.XENO_STEMS ? window.XENO_STEMS() : null;
  if (stems && stems.id) {
    params.set("stemsId", stems.id);
    params.set("stems", media(`/api/stems/${encodeURIComponent(stems.id)}/envelopes.json`));
  }
  return media(`/vj?${params.toString()}`);
}

// The MIDI drawer lives in the macro strip (ui_v6.js) inside Fine-tune: open both and focus it.
function openMidiDrawer() {
  const tune = document.getElementById("fine-tune");
  if (tune) tune.open = true;
  const midi = document.querySelector(".xf-midi");
  if (midi) {
    midi.open = true;
    const summary = midi.querySelector("summary");
    if (summary) summary.focus();
    midi.scrollIntoView({ block: "center" });
  }
}

function treatmentPanel() {
  const treatments = state.treatments || [];
  if (!treatments.length) return "";
  const cards = treatments
    .map((item) => {
      const on = item.id === state.treatment ? " on" : "";
      const moments = (item.moments || []).map((moment) => esc(moment)).join(" · ");
      return `<button type="button" class="treatment${on}" data-act="treatment" data-treatment="${esc(item.id)}"><strong>${esc(item.name)}</strong><span>${moments}</span><em>${esc(item.idea || "")}</em></button>`;
    })
    .join("");
  const bible = state.bible;
  const frames = bible
    ? (bible.frames || [])
        .map(
          (frame) => `<figure>
            <span class="swatch" style="background:${esc(frame.swatch || "#9b8cff")}"></span>
            <figcaption>${esc(frame.name || "")}</figcaption>
            <p>${esc(frame.prompt || "")}</p>
          </figure>`,
        )
        .join("")
    : "";
  const rules = bible ? (bible.motion || []).map((line) => `<li>${esc(line)}</li>`).join("") : "";
  const chosen = treatments.find((item) => item.id === state.treatment) || treatments[0] || {};
  const card = chosen.idea
    ? `<div class="treatment-card">
        <p><b>Idea</b> ${esc(chosen.idea)}</p>
        <p><b>Through-line</b> ${esc(chosen.through || "")}</p>
        <p><b>Lead</b> ${esc(chosen.lead || "")}</p>
        <p><b>Colour</b> ${esc(chosen.colour || "")}</p>
      </div>`
    : "";
  return `<section class="panel treatments-panel">
    <p class="kicker">Treatment · ${esc((bible && bible.look) || "Action Cut")}</p>
    <h2>Pick the three moments.</h2>
    <div class="treatments" data-tour="treatment">${cards}</div>
    ${card}
    ${
      bible
        ? `<p class="bible">${esc(bible.palette || "")}. ${esc((bible.textures || []).join(", "))}.</p>
           <ul class="motion-rules">${rules}</ul>
           <div class="swatches">${frames}</div>`
        : ""
    }
    <p class="note">The style frames are the look. Turbo plays a 4 second proof before the full animatic. The picture locks to the song.</p>
    <label class="idea-field">Look
      <input id="style-note" type="text" maxlength="80" value="${esc(state.styleNote || "")}" aria-label="Look and palette" autocomplete="off" />
    </label>
    <label class="idea-field">Transition
      <input id="transition-note" type="text" maxlength="140" value="${esc(state.transitionNote || "")}" aria-label="Transition or morph" autocomplete="off" />
    </label>
  </section>`;
}

function morphJoin() {
  const scenes = state.scenes || [];
  const signed = scenes.findIndex((scene) => scene.signature);
  const climax = scenes.findIndex((scene) => scene.beat === "climax");
  const index = signed > 0 ? signed : climax >= 0 ? climax : 0;
  return { index, scene: scenes[index] || null, before: scenes[Math.max(0, index - 1)] || null };
}

function morphQaChip() {
  const report = state && state.morphReport;
  if (!report || !report.joins) return `<span class="tl-qa">QA · not checked</span>`;
  if (!report.joins.length) return `<span class="tl-qa bad">QA · fail</span>`;
  const pass = report.joins.every((join) => join.qa && join.qa.pass);
  const detail = pass ? "pass" : "fail";
  return `<span class="tl-qa ${pass ? "ok" : "bad"}">QA · ${detail}</span>`;
}

function morphPanel() {
  const method = state.morphMethod || "keyframe-blend";
  const choices = [
    ["keyframe-blend", "Keyframe blend"],
    ["cross-clip", "Cross clip"],
    ["v2v-ramp", "Video ramp"],
    ["region-staged", "Staged region"],
  ]
    .map(([id, label]) => {
      const on = id === method ? " on" : "";
      const pressed = id === method ? "true" : "false";
      return `<button type="button" class="${on}" data-act="morph-method" data-method="${id}" aria-pressed="${pressed}">${label}</button>`;
    })
    .join("");
  const join = morphJoin();
  const source = join.before || join.scene || {};
  const clip = { wide: "wide", medium: "medium", close: "close", macro: "close", tracking: "medium", reveal: "reveal", overhead: "reveal" }[source.shot] || "wide";
  const number = join.index ? String(join.index).padStart(2, "0") : "01";
  return `<section class="panel span" id="morph-panel">
    <p class="kicker">Morph</p>
    <h2>Blend two shots that already exist</h2>
    <div class="morph-split">
      <figure class="morph-source">
        <video muted autoplay playsinline loop src="${esc(media("/static/library/" + clip + ".mp4"))}"></video>
        <figcaption>Source · shot ${number}</figcaption>
      </figure>
      <div>
        <p class="note">The blend names the two subjects in the brief and nothing from the register. A restyle uses LTX-2.3 when that file is on this machine. Fast stays on LTX 0.9.5. Seed 2727.</p>
        <div class="toggle" role="group" aria-label="Morph method">${choices}</div>
        <div class="morph-actions">
          <button type="button" class="${state.morphFast ? "on" : ""}" data-act="morph-fast" aria-pressed="${state.morphFast ? "true" : "false"}">Fast</button>
          <button type="button" class="${state.morphHit !== false ? "on" : ""}" data-act="morph-hit" aria-pressed="${state.morphHit !== false ? "true" : "false"}">Hit flash</button>
          <button type="button" class="ghost" data-act="morph-check">Check the joins</button>
          ${morphQaChip()}
        </div>
      </div>
    </div>
    <div id="morph-report">${morphReportHtml()}</div>
    <div id="library-browser" class="library-browser">
      <p class="kicker">Source library</p>
      <h3>Partners for this scene</h3>
      <p class="note" id="library-note">Reading the library…</p>
      <p class="library-pair" id="library-pair"></p>
      <label class="field">Filter by tag
        <input id="library-tag" type="search" value="${esc(state.libraryTag || "")}" aria-label="Filter the library by tag" autocomplete="off" />
      </label>
      <div class="library-grid" id="library-grid"></div>
    </div>
  </section>`;
}

function morphReportHtml() {
  const report = state && state.morphReport;
  if (!report) return "";
  if (!report.joins || !report.joins.length) {
    return `<p class="note">${esc(report.note || "No morph on this cut. Hard cuts only.")}</p>`;
  }
  const rows = report.joins
    .map((join) => {
      const qa = join.qa || {};
      const detail = qa.pass ? "Pass." : (qa.reasons || []).join(" ") || "Fail.";
      const hit = join.hit ? " Hit frame." : "";
      const why = join.reason ? `${join.reason} ` : "";
      return `<p>${esc(why)}${esc(join.method)} at ${clock(join.at || 0)}.${hit} ${esc(detail)}</p><p>${esc(join.prompt || "")}</p>`;
    })
    .join("");
  const note = report.note ? `<p class="note">${esc(report.note)}</p>` : "";
  return `${note}${rows}`;
}

async function previewAnimatic(button) {
  if (button) button.disabled = true;
  const note = document.getElementById("preview-note");
  if (note) note.textContent = "Cutting the animatic…";
  try {
    const response = await api("/api/animatic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_id: state.audioId || "demo",
        scenes: state.scenes || [],
      }),
    });
    if (!response.ok) {
      state.previewNote = "The preview did not cut.";
      if (note) note.textContent = state.previewNote;
      return;
    }
    const body = await response.json();
    state.previewUrl = body.url;
    state.previewNote = `Animatic · ${body.width}×${body.height} · cut in ${body.seconds}s`;
    render();
  } finally {
    if (button && button.isConnected) button.disabled = false;
  }
}

async function exportWorkflow(button) {
  if (button) button.disabled = true;
  try {
    const response = await api("/api/workflow", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenes: state.scenes || [],
        brief: state.brief || "",
        fps: state.fps || 12,
        seed: 2727,
        width: 512,
        height: 320,
        video_model: state.videoModel || "ltx-23",
      }),
    });
    if (!response.ok) return;
    const graph = await response.json();
    const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "xenoform-storyboard.json";
    link.click();
    URL.revokeObjectURL(url);
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadMorph() {
  if (!state) return;
  const response = await api("/api/morph/board", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scenes: state.scenes || [],
      beats: state.beats || [],
      sections: state.sections || [],
      drops: state.drops || [],
      method: state.morphMethod || "keyframe-blend",
      brief: state.brief || "",
      fast: !!state.morphFast,
      lock: true,
      hit: state.morphHit !== false,
    }),
  });
  const data = await response.json();
  if (!response.ok) return;
  state.morphReport = data;
  const slot = document.getElementById("morph-report");
  if (slot) slot.innerHTML = morphReportHtml();
  else render();
}

function energyWord(value) {
  const energy = Number(value || 0);
  if (energy <= 0) return "Calm";
  if (energy >= 1) return "Hype";
  return energy.toFixed(2);
}

function gateCopy() {
  if (state.gateReason) return state.gateReason;
  if (state.storyApproved) return "Shot list approved.";
  if (state.storyNudge) return "Approve the shot list before Turbo, Draft, or Final. Live stays in the browser.";
  return "Approve the shot list before a GPU render. Approve 1 or 2 test clips before a full batch. Live stays in the browser.";
}

function gateChecklist() {
  if (!state || state.quality === "live") return `<span class="gate-item">Live stays in the browser.</span>`;
  const clips = (state.testClips || []).length;
  const storyOk = !!state.storyApproved;
  const clipsOk = clips >= 1 && clips <= 2;
  const story = storyOk ? "Story approved ✓" : "Story";
  const approve = storyOk ? "" : `<button type="button" class="text" data-act="approve-story">Approve</button>`;
  const reason = state.gateReason ? `<span class="gate-reason">${esc(state.gateReason)}</span>` : "";
  const logic = state.logic && state.logic.ok === false ? `<span class="gate-reason">${esc(state.logic.detail || "The story has to hold in one line.")}</span>` : "";
  return `<span class="gate-item${storyOk ? " pass" : ""}">${story}</span><span class="gate-item${clipsOk ? " pass" : ""}">Test clips ${clips} of 1–2</span>${approve}${reason}${logic}`;
}

function paintGate() {
  const html = gateChecklist();
  document.querySelectorAll("[data-gate]").forEach((node) => {
    node.innerHTML = html;
  });
}

function shotRows() {
  return (state.scenes || [])
    .map(
      (scene, index) => `<li>
        <span class="num">${String(index + 1).padStart(2, "0")}</span>
        <span class="beat">${esc(scene.beat)}</span>
        <span class="when">${clock(scene.start)}</span>
        <span class="action">${esc(scene.action)}</span>
        <span class="who">${esc(scene.verb || "")} · ${esc(formName(scene.form))}</span>
        <span class="how">${esc(scene.shot)} · ${esc(scene.move)} · ${scene.bars} bar${scene.bars === 1 ? "" : "s"}</span>
      </li>`,
    )
    .join("");
}

function beatGridInner() {
  const grid = state.grid || { duration: state.duration || 1, beats: state.beats || [], cuts: [], morphs: [] };
  const duration = Number(grid.duration || state.duration || 1) || 1;
  const tick = (time, kind) => `<i class="${kind}" style="left:${(Number(time) / duration) * 100}%"></i>`;
  return (grid.beats || []).map((beat) => tick(beat, "beat")).join("")
    + (grid.cuts || []).map((cut) => tick(cut, "cut")).join("")
    + (grid.morphs || []).map((cut) => tick(cut, "morph")).join("");
}

function qaInner() {
  const report = state.qa;
  if (!report) return `<p class="note">The cut has not been measured yet.</p>`;
  const rows = [
    ["Sync", report.sync],
    ["Motion", report.motion],
    ["Morphs", report.morph],
    ["Flash", report.flash],
    ["Energy", report.energy],
  ];
  return `<ul class="qa-list">${rows
    .map(([label, row]) => {
      const pass = !!(row && row.pass);
      return `<li class="${pass ? "pass" : "fail"}"><span>${pass ? "Pass" : "Fail"}</span><b>${esc(label)}</b><em>${esc((row && row.detail) || "")}</em></li>`;
    })
    .join("")}</ul>`;
}

function storyInner() {
  const story = state.story || {};
  const journey = (story.journey || [])
    .map((step) => `<li><b>${esc(step.beat)}</b> ${esc(step.line || "")}</li>`)
    .join("");
  const shots = (story.shots || [])
    .map((scene, index) => {
      const because = scene.because ? `<em>${esc(scene.because)}</em>` : "";
      return `<li><span>${String(index + 1).padStart(2, "0")}</span> ${esc(scene.shot || "")} · ${esc(scene.action || "")}${because}</li>`;
    })
    .join("");
  const gpu = story.gpu || { seconds: 0, line: "no GPU" };
  const gpuText = gpu.seconds
    ? `${gpu.seconds}s of GPU time for ${qualityLabel(state.quality)}. ${gpu.line}`
    : "No GPU. This cut is assembled from cached shots.";
  return `<div id="continuity-story">
    <p class="logline">${esc(story.logline || state.brief || "")}</p>
    <p class="hero-line"><b>Hero</b> ${esc(story.hero || "The protagonist is still unnamed.")}</p>
    <ol class="journey">${journey || `<li>The journey appears with the shot list.</li>`}</ol>
    <ol class="story-shots">${shots}</ol>
    ${continuityInner()}
    </div>
    <p class="gpu" id="gpu-line" data-tour="gate">${esc(gpuText)}</p>`;
}

function continuityInner() {
  const bible = state.continuity;
  if (!bible || !(bible.elements || []).length) return "";
  const rows = (bible.elements || [])
    .map((element) => {
      const still = element.url
        ? `<img alt="${esc(element.name || "Reference")}" src="${esc(media(element.url))}" />`
        : `<span class="frame-wait">Still</span>`;
      const kicker = element.kind === "hero" ? "Cast lock" : element.kind || "";
      return `<article class="continuity-row">
        <figure>${still}</figure>
        <p><b>${esc(kicker)}</b> ${esc(element.sentence || "")}</p>
      </article>`;
    })
    .join("");
  const flags = ((state.logic && state.logic.flags) || [])
    .map((flag) => `<li>${esc(flag.plain || "")}</li>`)
    .join("");
  const what = bible.what || (state.logic && state.logic.what) || "";
  return `<div class="continuity-card" id="continuity-card" data-tour="continuity">
    <p class="kicker">Continuity</p>
    <p class="what-happens"><b>What happens</b> ${esc(what)}</p>
    <div class="continuity-rows">${rows}</div>
    ${flags ? `<ul class="continuity-flags">${flags}</ul>` : `<p class="note">One hero, one of each prop, one place. Each shot follows from the last.</p>`}
  </div>`;
}

function timingPanel() {
  const duration = Number(state.duration || 1) || 1;
  const sections = (state.sections || [])
    .map((section) => {
      const width = Math.max(4, ((Number(section.end) - Number(section.start)) / duration) * 100);
      return `<span class="sec sec-${esc(section.label || "sustain")}" style="width:${width}%">${esc(section.label || "")}</span>`;
    })
    .join("");
  const lyric = state.lyricOn ? " checked" : "";
  const words = (state.lyricWords || []).map((word) => `<i>${esc(word.word)}</i>`).join(" ");
  return `<section class="panel span timing-panel" id="timing-panel" data-tour="beats">
    <p class="kicker">Song timing</p>
    <h2>The beat grid, before any picture</h2>
    <div class="beat-grid" aria-hidden="true">${beatGridInner()}</div>
    <div class="legend">
      <span><i class="sw-beat"></i>beat</span>
      <span><i class="sw-cut"></i>cut</span>
      <span><i class="sw-morph"></i>morph</span>
    </div>
    <div class="timing-map" aria-label="Section map">${sections}</div>
    <label class="check"><input id="lyric-align" type="checkbox"${lyric} /> Lyric align</label>
    <p class="note">Off by default. Local open weights only. Whisper runs 0.3–1.5s early, so a correction offset moves the words later. ${esc(state.lyricNote || "")}</p>
    <div class="title-row">
      <label>Offset, seconds
        <input id="lyric-offset" type="number" min="0.3" max="1.5" step="0.1" value="${Number(state.lyricOffset || 0.9)}" aria-label="Lyric offset in seconds"${state.lyricOn ? "" : " disabled"} />
      </label>
      <label>Local transcript
        <textarea id="lyric-words" rows="2" aria-label="Local transcript" placeholder="word 1.20 1.48"${state.lyricOn ? "" : " disabled"}>${esc(state.lyricDraft || "")}</textarea>
      </label>
    </div>
    <p class="lyric-line">${words}</p>
  </section>`;
}

function takeSeed(index) {
  const picked = (state.takes || []).find((take) => take.scene === index && take.picked);
  if (picked) return Number(picked.seed);
  const owned = (state.takes || []).filter((take) => take.scene === index);
  if (!owned.length) return 2727;
  return Number(owned[owned.length - 1].seed);
}

function shotReview() {
  const rows = (state.scenes || [])
    .map((scene, index) => {
      const seed = takeSeed(index);
      const prompt = scene.prompt || scene.action || "";
      const clip = { wide: "wide", medium: "medium", close: "close", macro: "close", tracking: "medium", reveal: "reveal", overhead: "reveal" }[scene.shot] || "wide";
      const key = `${index}:${seed}`;
      const frame = (state.frameUrls || {})[key] || "";
      const still = frame
        ? `<img alt="Keyframe ${index + 1}" src="${esc(frame)}" />`
        : `<span class="frame-wait">Keyframe</span>`;
      const takes = (state.takes || [])
        .filter((take) => take.scene === index)
        .map((take) => {
          const on = take.picked ? " on" : "";
          return `<button type="button" class="take${on}" data-act="pick-take" data-index="${index}" data-seed="${take.seed}">${take.seed}${take.repeated ? " · repeat" : ""}</button>`;
        })
        .join("");
      const approved = (state.testClips || []).includes(String(index)) ? " checked" : "";
      return `<article class="review-shot">
        <header><b>${String(index + 1).padStart(2, "0")}</b> ${esc(scene.shot || "")} · seed ${seed}</header>
        <div class="review-row">
          <figure>${still}<figcaption>Keyframe</figcaption></figure>
          <figure><video muted autoplay playsinline loop src="${esc(media("/static/library/" + clip + ".mp4"))}"></video><figcaption>Clip</figcaption></figure>
        </div>
        <label>Prompt
          <textarea data-prompt="${index}" rows="2" maxlength="240" aria-label="Prompt for shot ${index + 1}">${esc(prompt)}</textarea>
        </label>
        <div class="cut-actions">
          <button type="button" class="generate" data-act="remake" data-index="${index}">Remake</button>
          <button type="button" class="ghost" data-act="new-take" data-index="${index}">New seed</button>
          <label class="check"><input type="checkbox" data-act="test-clip" data-index="${index}"${approved} /> Test clip</label>
        </div>
        <div class="takes">${takes}</div>
      </article>`;
    })
    .join("");
  return `<section class="panel span review-desk" id="review-desk">
    <p class="kicker">Shot review</p>
    <h2>Keyframe beside the clip</h2>
    <p class="note">Remake with the same seed repeats the take. A new seed keeps the old take and adds one. A text-only change re-renders that shot. Titles and lyrics are drawn in code, not in the prompt.</p>
    ${rows}
  </section>`;
}

function cutPanel() {
  const hero = state.heroUrl
    ? `<img class="hero-thumb" alt="Hero reference" src="${esc(media(state.heroUrl))}" />`
    : "";
  const continuous = state.continuous ? " checked" : "";
  return `<section class="panel span cut-panel" id="cut-panel">
    <p class="kicker">Cut</p>
    <h2>Calm to Hype, from the shots you already have</h2>
    <div class="energy-labels"><span>Calm</span><b id="energy-readout">${esc(energyWord(state.energy))}</b><span>Hype</span></div>
    <input id="energy" type="range" min="0" max="1" step="0.01" value="${Number(state.energy || 0)}" aria-label="Energy from Calm to Hype" />
    <p class="note">Calm is the default. The slider re-cuts cached shots on the beat grid. Morphs stay at two or fewer. Nothing here calls the GPU.</p>
    <div class="beat-grid" id="beat-grid" aria-hidden="true">${beatGridInner()}</div>
    <div class="legend">
      <span><i class="sw-beat"></i>beat</span>
      <span><i class="sw-cut"></i>cut</span>
      <span><i class="sw-morph"></i>morph</span>
    </div>
    <div class="story-grid">
      <div>
        <p class="kicker">Story</p>
        <div id="story-body">${storyInner()}</div>
        <p class="note" id="story-gate">${esc(gateCopy())}</p>
        <div class="cut-actions">
          <button type="button" class="generate" id="approve-story" data-act="approve-story">${state.storyApproved ? "Approved" : "Approve shot list"}</button>
          <button type="button" class="ghost" data-act="conform">${state.heldBoard ? "Conform the saved story to this song" : "Conform this story to the song"}</button>
        </div>
      </div>
      <div>
        <p class="kicker">Hero lock</p>
        <div class="hero-row">
          ${hero}
          <label class="upload">Reference image<input id="hero-file" type="file" accept="image/png,image/jpeg,image/webp" /></label>
        </div>
        <p class="note">One picture of the protagonist is the first frame of every shot.</p>
        <label class="check"><input id="continuous" type="checkbox"${continuous} /> Continuous take</label>
        <p class="note">Chain the last frame of each shot to the first frame of the next, and snap the hit onto the beat.</p>
        <div class="title-row">
          <label>Title card
            <input id="title-card" type="text" maxlength="80" value="${esc(state.titleText || "")}" aria-label="Title card" />
          </label>
          <label>End card
            <input id="end-card" type="text" maxlength="80" value="${esc(state.endText || "")}" aria-label="End card" />
          </label>
        </div>
        <div id="qa-panel">${qaInner()}</div>
      </div>
    </div>
  </section>`;
}

function renderSimple() {
  const lead = (state.scenes || [])[0] || {};
  const spine = lead.protagonist
    ? `<p class="spine"><b>${esc(lead.protagonist)}</b> · ${esc(lead.goal || "")}<br>${esc(lead.payoff || "")}</p>`
    : "";
  const rows = shotRows();
  return `<div class="simple">
    <section class="panel span song-drop" data-tour="song">
      <p class="kicker">Song</p>
      <h2>Pick or drop a song</h2>
      <div class="song-actions">
        <label class="upload">Drop a song<input id="song-file" type="file" accept="audio/*,.wav,.mp3,.flac,.ogg" aria-label="Drop a song" /></label>
        <button type="button" class="ghost" data-act="use-demo">Use the bundled demo</button>
      </div>
      <p class="note" id="song-note">The desk opens on examples/demo.wav. Drop a file to analyze another track. Nothing here starts a render.</p>
    </section>
    <section class="panel span guided-tours" id="guided-tours">
      <p class="kicker">Guided tours</p>
      <h2>Short walks through the desk</h2>
      <div id="tour-list"><p class="note">Opening the tours…</p></div>
    </section>
    ${timingPanel()}
    <section class="panel stage span">
      <p class="kicker">Picture · ${esc(qualityLabel(state.quality))}</p>
      <h2>${esc(state.quality === "live" ? "Live" : state.videoLabel || "Picture")}</h2>
      ${stageMedia()}
      <p class="caption"><b>${esc(registerName())}</b> · seed 2727 · ${esc(paletteLabel())}</p>
      ${qualityToggle()}
    </section>
    ${cutPanel()}
    ${morphPanel()}
    <section class="panel brief-panel">
      <p class="kicker">Overview</p>
      <h2>Tell it the life. It cuts the song.</h2>
      <label class="brief-label" for="brief">One-line brief</label>
      <textarea id="brief" rows="3" maxlength="180" aria-label="One-line brief">${esc(state.brief || "")}</textarea>
      <p class="note">One line becomes a protagonist, a goal, and a payoff. Each section is an action shot, hard-cut on the bar. A morph is a signature, once, on the drop. It plans offline. A local model is used only if <span class="mono">XENO_LLM_URL</span> is set.</p>
      <div class="simple-actions">
        <button type="button" class="generate" data-act="try-it">Try the demo</button>
        <button type="button" class="ghost" data-act="generate-inline">Generate this brief</button>
        <div class="generate-gate" data-gate="1"></div>
        <button type="button" class="ghost" data-act="to-director">Open the storyboard</button>
        <button type="button" class="ghost" data-act="music-only">Music only</button>
        <button type="button" class="ghost" data-act="share-cut" data-tour="share">Share cut</button>
      </div>
      ${setupBanner()}
    </section>
    <section class="panel">
      <p class="kicker">Shot list · ${esc(state.planner || "template")}</p>
      <h2>${esc(registerName())}</h2>
      ${spine}
      <ol class="shotlist">${rows}</ol>
    </section>
    ${shotReview()}
    ${treatmentPanel()}
    ${bandMap()}
  </div>`;
}

function sceneEditor() {
  const scene = (state.scenes || [])[state.expanded];
  if (!scene) return "";
  const forms = allForms()
    .map((form) => `<option value="${esc(form.id)}"${form.id === scene.form ? " selected" : ""}>${esc(form.name)}</option>`)
    .join("");
  return `<section class="panel editor" id="scene-editor">
    <p class="kicker">Scene ${String(scene.index + 1).padStart(2, "0")} · ${esc(scene.beat)}</p>
    <h2>${esc(scene.action)}</h2>
    <div class="editor-grid">
      <label>Action
        <textarea data-scene="action" data-index="${scene.index}" rows="3" maxlength="180" aria-label="Action">${esc(scene.action)}</textarea>
      </label>
      <label>Verb
        <input data-scene="verb" data-index="${scene.index}" type="text" maxlength="40" value="${esc(scene.verb || "")}" aria-label="Action verb" />
      </label>
      <label>Protagonist
        <input data-scene="protagonist" data-index="${scene.index}" type="text" maxlength="80" value="${esc(scene.protagonist || "")}" aria-label="Protagonist" />
      </label>
      <label>Goal
        <input data-scene="goal" data-index="${scene.index}" type="text" maxlength="160" value="${esc(scene.goal || "")}" aria-label="Goal" />
      </label>
      <label>Payoff
        <input data-scene="payoff" data-index="${scene.index}" type="text" maxlength="160" value="${esc(scene.payoff || "")}" aria-label="Payoff" />
      </label>
      <label>Subject
        <select data-scene="form" data-index="${scene.index}" aria-label="Subject">${forms}</select>
      </label>
      <label>Shot
        <select data-scene="shot" data-index="${scene.index}" aria-label="Shot">${choiceOptions(state.shots, scene.shot)}</select>
      </label>
      <label>Camera
        <select data-scene="move" data-index="${scene.index}" aria-label="Camera move">${choiceOptions(state.moves, scene.move)}</select>
      </label>
      <label>Edit
        <select data-scene="edit" data-index="${scene.index}" aria-label="Edit">${choiceOptions(state.edits, scene.edit)}</select>
      </label>
      <label>Mood and light
        <select data-scene="mood" data-index="${scene.index}" aria-label="Mood and light">${choiceOptions(state.moods, scene.mood)}</select>
      </label>
      <label>Duration, bars
        <input data-scene="bars" data-index="${scene.index}" type="number" min="1" max="64" step="1" value="${scene.bars}" aria-label="Duration in bars" />
      </label>
      <p class="note">Snapped to the bar (${(scene.bar_seconds || 2).toFixed(2)}s). The first frame is the guide. The shot plays the action. A morph is a signature.</p>
    </div>
  </section>`;
}

function renderDirector() {
  const open = state.view === "scene" || state.expanded != null;
  const presets = (state.presets || [])
    .map((preset) => {
      const on = preset.id === state.preset ? " on" : "";
      return `<button type="button" class="preset${on}" data-act="preset" data-preset="${esc(preset.id)}"><strong>${esc(preset.name)}</strong><span>${esc(preset.note)}</span></button>`;
    })
    .join("");
  const arc = ["setup", "rising", "climax", "release"]
    .map((beat) => `<span class="${(state.scenes || []).some((scene) => scene.beat === beat) ? "on" : ""}">${beat}</span>`)
    .join("<i></i>");
  return `<div class="director">
    <section class="panel span">
      <div class="board-head">
        <div>
          <p class="kicker">Director</p>
          <h2>Storyboard</h2>
        </div>
        <p>One card per section. A protagonist, a goal, a payoff. Hard cuts on the bar. A morph is a signature, once or twice, usually on the drop. Drag the climax onto a card. A callback is the last line.</p>
      </div>
      <div class="story-tools">
        <label>Brief
          <input id="brief" type="text" maxlength="180" value="${esc(state.brief || "")}" aria-label="Brief" />
        </label>
        <label>Callback
          <input id="callback" type="text" maxlength="140" value="${esc(state.callback || "")}" placeholder="the sphere returns at the end, changed" aria-label="Callback" />
        </label>
        <div class="climax-chip" draggable="true" id="climax-token" title="Drag onto a scene">Climax</div>
      </div>
      <div class="beat-rail" aria-hidden="true">${arc}</div>
      <div class="scene-grid">${sceneCards()}</div>
      ${treatmentPanel()}
    </section>
    ${open ? sceneEditor() : ""}
    <section class="panel span">
      <p class="kicker">Song</p>
      <h2>${esc(state.title)}</h2>
      <div class="wave-wrap"><canvas class="wave" id="wave" width="640" height="220"></canvas></div>
      <div class="legend">
        <span><i class="sw-section"></i>section</span>
        <span><i class="sw-drop"></i>drop</span>
        <span><i class="sw-beat"></i>beat</span>
      </div>
      <div class="song-actions">
        <label class="upload">Replace song<input id="song-file" type="file" accept="audio/*,.wav,.mp3,.flac,.ogg" /></label>
        <button type="button" class="ghost" data-act="music-only">Music only</button>
        <button type="button" class="ghost" data-act="share-cut">Share cut</button>
      </div>
    </section>
    ${timingPanel()}
    ${cutPanel()}
    ${morphPanel()}
    ${shotReview()}
    <section class="panel picture span">
      <div class="picture-split">
        <div class="stage">
          <p class="kicker">Picture</p>
          <h2>${esc(state.quality === "live" ? "Live" : state.videoLabel || "Picture")}</h2>
          ${stageMedia()}
          ${qualityToggle()}
          ${stagesHtml()}
        </div>
        ${notesPanel()}
      </div>
    </section>
    ${bandMap()}
    <section class="panel">
      <div data-tour="looks">
        <div class="looks-head">
          <div>
            <p class="kicker">Looks</p>
            <h2>${esc(lookName())}</h2>
          </div>
          <button type="button" class="generate" data-act="random">Roll the board</button>
        </div>
        <div class="preset-grid">${presets}</div>
      </div>
      <div class="recipe-code" id="recipe-out">${esc(state.recipe)}</div>
      <div class="recipe-actions">
        <button type="button" class="ghost" data-act="copy">Copy</button>
        <input id="recipe-in" type="text" spellcheck="false" placeholder="XF-…" aria-label="Paste a recipe" />
        <button type="button" class="ghost" data-act="restore">Restore</button>
      </div>
      <p class="hint" id="recipe-hint"></p>
      <p class="note">The code carries the storyboard: brief, scenes, callback, motif, and the register. ${lockButton("script", "storyboard")}</p>
    </section>
  </div>`;
}

function notesPanel() {
  const pending = state.pending;
  const chips = (state.suggestions || [])
    .map(
      (item) =>
        `<button type="button" class="chip" data-act="chip" data-note="${esc(item.note)}" title="${esc(item.reason || "")}">${esc(item.note)}</button>`,
    )
    .join("");
  const diff = pending
    ? (pending.diff || [])
        .map(
          (row) => `<article>
            <p class="field">${esc(row.label)} · ${esc(row.field)}</p>
            <p class="old">${esc(row.old)}</p>
            <p class="new">${esc(row.new)}</p>
          </article>`,
        )
        .join("")
    : "";
  const patch = pending && pending.patch ? JSON.stringify(pending.patch, null, 2) : "";
  const versions = (state.versions || [])
    .map((version, index) => {
      const on = version.id === state.versionId ? " on" : "";
      return `<li class="${on.trim()}">
        <button type="button" class="watch" data-act="watch-version" data-id="${esc(version.id)}">v${index + 1} · ${esc(version.label || version.note || "Cut")}</button>
        <button type="button" class="text" data-act="revert-version" data-id="${esc(version.id)}">Revert</button>
      </li>`;
    })
    .join("");
  const open = state.notesOpen || pending ? " open" : "";
  const offer = (pending && pending.lesson_offer) || state.lessonOffer;
  const offerHtml = offer
    ? `<div class="lesson-offer">
        <p>${esc(offer.prompt || "Save this as a lesson.")}</p>
        <p class="rule">${esc(offer.rule || "")}</p>
        <div class="note-actions">
          <button type="button" class="generate" data-act="save-lesson">Save as a lesson</button>
          <button type="button" class="ghost" data-act="dismiss-lesson">Not now</button>
        </div>
      </div>`
    : "";
  const learned = (state.savedLessons || [])
    .map((lesson) => `<li>${esc(lesson.lesson || lesson.note)}</li>`)
    .join("");
  let source = "";
  if (pending) {
    if (pending.source === "lesson") source = "Saved lesson, on this machine";
    else if (pending.source === "llm") source = `Local model · ${pending.model || "ollama"}`;
    else if (pending.source === "rules-fallback") source = "Rules, after the model reply failed the schema";
    else source = "Rules, on this machine";
  }
  return `<aside class="notes">
    <p class="kicker">Director's notes</p>
    <h2>Watch, then say what to change</h2>
    <textarea id="note-text" rows="3" maxlength="400" placeholder="${esc(SAMPLE_NOTE)}" aria-label="Director's note">${esc(state.note || "")}</textarea>
    <div class="notes-apply">
      <button type="button" class="generate${state.noteBusy ? " is-loading" : ""}" data-act="apply-note"${state.noteBusy ? " disabled" : ""}>Apply</button>
      <span class="note-status">${esc(state.noteStatus || "One box. The patch waits for confirm.")}</span>
    </div>
    <div class="chips" aria-label="Critic suggestions">${chips || `<p class="note">The critic has nothing loud to flag.</p>`}</div>
    <details class="note-depth"${open}>
      <summary>Patch, versions, compare</summary>
      ${
        pending
          ? `<p class="source">${esc(source)}</p>
             <pre class="patch">${esc(patch)}</pre>
             <div class="diff">${diff}</div>
             <p class="rationale">${esc(pending.rationale || "")}</p>
             <p class="cache-line">${esc(pending.cache_line || "")}</p>
             <div class="note-actions">
               <button type="button" class="generate${state.noteBusy ? " is-loading" : ""}" data-act="confirm-note"${state.noteBusy ? " disabled" : ""}>Confirm</button>
               <button type="button" class="ghost" data-act="undo-note">Undo</button>
             </div>
             ${offerHtml}`
          : `<p class="note">Apply a note to see the patch and the diff before anything renders.</p>`
      }
      ${learned ? `<p class="kicker">Lessons learned</p><ul class="learned">${learned}</ul>` : `<p class="note">Saved lessons become critic rules on the next cut.</p>`}
      <ol class="versions">${versions || `<li class="empty"><span>Versions appear as you confirm notes.</span></li>`}</ol>
      <p class="kicker">Review ledger</p>
      ${
        (state.ledger || []).length
          ? `<ol class="ledger">${(state.ledger || [])
              .map(
                (row) =>
                  `<li>Round ${esc(String(row.round))} · ${esc(row.verdict || "")} · ${esc(
                    (row.before && row.before.failed) || "",
                  )}</li>`,
              )
              .join("")}</ol>${state.ledgerMarkdown ? `<pre class="patch ledger-raw">${esc(state.ledgerMarkdown)}</pre>` : ""}`
          : `<p class="note">The ledger fills after the first review.</p>`
      }
      <div class="note-actions">
        <button type="button" class="ghost" data-act="flip">Flip A/B</button>
      </div>
    </details>
  </aside>`;
}

function renderNotes() {
  return `<div class="notes-view">
    <section class="panel stage">
      <p class="kicker">${esc(qualityLabel(state.quality))}</p>
      <h2>${esc(state.quality === "live" ? "Live" : state.videoLabel || "Picture")}</h2>
      ${stageMedia()}
      <p class="caption"><b>${esc(registerName())}</b> · seed 2727 · ${esc(state.quality || "draft")} · ${esc(state.videoLabel || "Reference")}</p>
      ${stagesHtml()}
    </section>
    <section class="panel notes-pane">${notesPanel()}</section>
  </div>`;
}

function snippetBlock(title, id, text, hint) {
  return `<section class="snippet">
    <header><h3>${esc(title)}</h3><button type="button" class="text" data-act="copy-snippet" data-snippet="${id}">Copy</button></header>
    <p class="note">${hint}</p>
    <pre id="snippet-${id}">${esc(text)}</pre>
  </section>`;
}

function connectSnippets() {
  const desk = location.origin || "http://127.0.0.1:47317";
  const stdio = JSON.stringify({
    mcpServers: {
      xenoform: {
        command: "xenoform",
        args: ["mcp"],
        env: { XENO_DESK: desk },
      },
    },
  }, null, 2);
  const http = JSON.stringify({
    mcpServers: {
      xenoform: { url: "http://127.0.0.1:47319/mcp" },
    },
  }, null, 2);
  return { stdio, http, desk };
}

function renderConnect() {
  const snippets = connectSnippets();
  const status = state.mcp || { detail: "The desk API is up. The agent port is off until you start it.", running: false };
  return `<section class="panel connect">
    <p class="kicker">Agent</p>
    <h2>Connect an AI</h2>
    <p class="note">Grok, Claude, GPT, or Cursor can direct this desk. The agent port is off until you start it, listens only on this machine, and needs no token. The desk it talks to is ${esc(snippets.desk)}.</p>
    <p class="mcp-status" id="mcp-status" data-running="${status.running ? "yes" : "no"}">${esc(status.detail || "")}</p>
    <div class="review-actions">
      <button type="button" class="ghost" data-act="mcp-test">Test connection</button>
      <button type="button" class="generate${state.mcpBusy ? " is-loading" : ""}" data-act="mcp-start"${state.mcpBusy ? " disabled" : ""}>Start on this machine</button>
    </div>
    ${snippetBlock("Claude Desktop", "claude", snippets.stdio, "Paste into claude_desktop_config.json. This uses stdio, so the HTTP port can stay off.")}
    ${snippetBlock("Cursor", "cursor", snippets.stdio, "Paste into .cursor/mcp.json. Same command. XENO_DESK is this desk.")}
    ${snippetBlock("Generic MCP client", "http", snippets.http, "Streamable HTTP at http://127.0.0.1:47319/mcp. Press Start on this machine first.")}
  </section>`;
}

const V6_VIBES = [
  {"id": "chrome-mercury", "name": "Liquid chrome", "line": "A mirror-chrome drop pours itself into the next form.", "palette": "silver", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/chrome-mercury.jpg", "featured": true},
  {"id": "neon-noir", "name": "Neon noir", "line": "Wet streets, magenta and cyan rim light, rain in the haze.", "palette": "magenta-cyan", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/neon-noir.jpg", "featured": true},
  {"id": "porcelain-kintsugi", "name": "Porcelain & gold", "line": "White porcelain that cracks open in gold on the beat.", "palette": "ivory-gold", "register": "pynchon", "morph": true, "dark": false, "tone": "bright", "still": "/static/vibes/porcelain-kintsugi.jpg", "featured": true},
  {"id": "bioluminescent", "name": "Deep-sea glow", "line": "Deep-sea forms that glow from inside.", "palette": "teal-violet", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/bioluminescent.jpg", "featured": true},
  {"id": "risograph", "name": "Risograph", "line": "Two-colour print grain, inks sliding out of register.", "palette": "pink-blue", "register": "pynchon", "morph": true, "dark": false, "tone": "bright", "still": "/static/vibes/risograph.jpg", "featured": true},
  {"id": "iridescent-glass", "name": "Iridescent glass", "line": "Blown glass with a rainbow film and swimming caustics.", "palette": "pearl-rainbow", "register": "pynchon", "morph": true, "dark": false, "tone": "bright", "still": "/static/vibes/iridescent-glass.jpg", "featured": true},
  {"id": "liquid-gold", "name": "Molten gold", "line": "Molten gold that pours, drips and cools to a polish.", "palette": "gold", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/liquid-gold.jpg", "featured": true},
  {"id": "ink-wash", "name": "Ink & paper", "line": "Sumi ink blooming across wet paper.", "palette": "sumi", "register": "pynchon", "morph": true, "dark": false, "tone": "bright", "still": "/static/vibes/ink-wash.jpg", "featured": true},
  {"id": "cyberspace-95", "name": "Cyberspace 1995", "line": "Green wireframe on an endless grid, 1995.", "palette": "green-cyan", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/cyberspace-95.jpg", "featured": true},
  {"id": "wet-paint", "name": "Wet paint", "line": "Thick glossy paint folding into the next shape.", "palette": "primary", "register": "pynchon", "morph": true, "dark": false, "tone": "bright", "still": "/static/vibes/wet-paint.jpg", "featured": true},
  {"id": "shadow-self", "name": "Shadow self", "line": "A backlit silhouette and smoke in one shaft of light.", "palette": "noir", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/shadow-self.jpg", "featured": true},
  {"id": "botanical", "name": "Bloom timelapse", "line": "A single bloom on black, scrubbed by the song.", "palette": "natural", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/botanical.jpg", "featured": true}
];
const VIBES_LEGACY = [
  {
    id: "liquid-gold",
    name: "Liquid gold",
    line: "A gold pour becomes a ring in a dark forge.",
    palette: "gold",
    register: "pynchon",
    morph: true,
    dark: false,
    tone: "bright",
    still: "/static/vibes/liquid-gold.jpg",
  },
  {
    id: "paper-summer",
    name: "Paper summer",
    line: "A paper boat crosses a bright kitchen.",
    palette: "neutral",
    register: "rome",
    morph: false,
    dark: false,
    tone: "bright",
    still: "/static/vibes/paper-summer.jpg",
  },
  {
    id: "bloom",
    name: "Bloom",
    line: "A flower opens on a green hill.",
    palette: "bronze",
    register: "tolkien",
    morph: false,
    dark: false,
    tone: "soft",
    still: "/static/vibes/bloom.jpg",
  },
  {
    id: "neon-night",
    name: "Neon night",
    line: "A neon sign holds one quiet street.",
    palette: "violet",
    register: "lecarre",
    morph: false,
    dark: true,
    tone: "dark",
    still: "/static/vibes/neon-night.jpg",
  },
  {
    id: "ocean",
    name: "Ocean",
    line: "A swimmer crosses a calm harbour.",
    palette: "grey-green",
    register: "tolkien",
    morph: false,
    dark: false,
    tone: "bright",
    still: "/static/vibes/ocean.jpg",
  },
  {
    id: "cosmic",
    name: "Cosmic",
    line: "A star field turns over a dark shore.",
    palette: "violet",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/cosmic.jpg",
  },
  {
    id: "black",
    name: "Black",
    line: "Black glass grows from one living form into the next.",
    palette: "violet",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/black.jpg",
  },
  {
    id: "chrome-mercury",
    name: "Chrome mercury",
    line: "A mirror-chrome droplet pours itself into the next form.",
    palette: "silver",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/chrome-mercury.jpg",
  },
  {
    id: "ferrofluid",
    name: "Ferrofluid",
    line: "Black magnetic liquid bristles into spikes on the kick.",
    palette: "graphite",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/ferrofluid.jpg",
  },
  {
    id: "y2k-chrome",
    name: "Y2K chrome",
    line: "Inflated chrome and frosted ice-blue plastic, millennium-clean.",
    palette: "ice-blue",
    register: "pynchon",
    morph: true,
    dark: false,
    tone: "bright",
    still: "/static/vibes/y2k-chrome.jpg",
  },
  {
    id: "low-poly",
    name: "Low-poly 32-bit",
    line: "Flat-shaded polygons from a late-90s console intro.",
    palette: "primary",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/low-poly.jpg",
  },
  {
    id: "odd-machine",
    name: "Odd machine",
    line: "Rubbery biomechanics twitch with uncanny precision.",
    palette: "flesh-steel",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/odd-machine.jpg",
  },
  {
    id: "brutalist",
    name: "Brutalist",
    line: "Raw concrete monoliths under a hard sun.",
    palette: "concrete",
    register: "pynchon",
    morph: true,
    dark: false,
    tone: "bright",
    still: "/static/vibes/brutalist.jpg",
  },
  {
    id: "porcelain-marble",
    name: "Porcelain marble",
    line: "White marble and blue-glazed porcelain on black velvet.",
    palette: "white-cobalt",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/porcelain-marble.jpg",
  },
  {
    id: "lava-obsidian",
    name: "Lava obsidian",
    line: "Glowing magma cracks through black volcanic glass.",
    palette: "magma",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/lava-obsidian.jpg",
  },
  {
    id: "ice-crystal",
    name: "Ice crystal",
    line: "Backlit frost crystals grow and fracture.",
    palette: "glacier",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/ice-crystal.jpg",
  },
  {
    id: "origami-noir",
    name: "Origami noir",
    line: "Black and gold-foil paper folds itself into new forms.",
    palette: "black-gold",
    register: "pynchon",
    morph: true,
    dark: true,
    tone: "dark",
    still: "/static/vibes/origami-noir.jpg",
  },
];
let VIBES = V6_VIBES.concat(VIBES_LEGACY.filter((v) => !V6_VIBES.some((f) => f.id === v.id)).map((v) => Object.assign({}, v, {legacy: true})));
// vibe id -> the library folder its 4-shot strip lives in (its own, or the pool it borrows stills from)
const VIBE_LIBRARY = {};
let LOOKS = null; // dance_fx presets with their one-line notes, from /api/vibes

function vibeById(id) {
  return VIBES.find((item) => item.id === id) || null;
}

// GET /api/vibes is the single source of truth (vibes.catalog()). The arrays above are the offline fallback.
async function loadVibes() {
  try {
    const res = await api("/api/vibes");
    if (!res.ok) return false;
    const body = await res.json();
    const rows = (body.vibes || []).filter((row) => row && row.id && row.name);
    if (!rows.length) return false;
    VIBES = rows.map((row) => Object.assign({}, row, { still: row.still || `/static/vibes/${row.id}.jpg`, legacy: !!row.legacy }));
    rows.forEach((row) => {
      VIBE_LIBRARY[row.id] = row.library || (row.has_library ? row.id : row.pool || row.id);
    });
    if (Array.isArray(body.looks) && body.looks.length) LOOKS = body.looks;
    return true;
  } catch (err) {
    return false;
  }
}

function libraryFolder(vibe) {
  return VIBE_LIBRARY[vibe] || vibe;
}

function energyFromTrack() {
  const levels = (state.sections || []).map((section) => Number(section.level || 0));
  const peak = levels.length ? Math.max.apply(null, levels) : 0;
  return Math.max(0, Math.min(1, peak || 0));
}

function plainWords(text) {
  return String(text || "")
    .replace(/LTX[-\w.]*/gi, "")
    .replace(/\b(turbo|draft|final|denoise|comfyui|seed)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function libraryClip(vibe, shot) {
  return media(`/static/library/${libraryFolder(vibe)}/${shot}.mp4`);
}

function libraryStill(vibe, shot) {
  return media(`/static/library/${libraryFolder(vibe)}/${shot}.jpg`);
}

function songFacts() {
  const duration = Number((state && state.duration) || 0);
  const tempo = Math.round(Number((state && state.tempo) || 0));
  const sections = ((state && state.sections) || []).length;
  const clock = duration ? `${Math.floor(duration / 60)}:${String(Math.floor(duration % 60)).padStart(2, "0")}` : "";
  return [clock, tempo ? `${tempo} BPM` : "", sections ? `${sections} sections` : ""].filter(Boolean).join(" · ");
}

function waveBars() {
  const peaks = (state && state.waveform) || [];
  const count = 42;
  const bars = [];
  for (let index = 0; index < count; index += 1) {
    const sample = peaks.length ? peaks[Math.floor((index / count) * peaks.length)] : 0.35;
    const value = typeof sample === "number" ? sample : Number(sample && sample.peak != null ? sample.peak : sample);
    const scaled = Number.isFinite(value) ? (value > 2 ? value / 100 : value) : 0.35;
    const height = Math.max(4, Math.round(Math.min(1, scaled) * 28));
    bars.push(`<i style="height:${height}px"${index < 16 ? ' class="on"' : ""}></i>`);
  }
  return `<span class="wave" aria-hidden="true">${bars.join("")}</span>`;
}

const SHOWCASE = { video: "/static/showcase/showcase.mp4", poster: "/static/showcase/showcase.jpg" };

function easyMedia() {
  if (state.easy && state.easy.showcase) {
    return `<video id="player" playsinline autoplay controls preload="auto" poster="${esc(media(SHOWCASE.poster))}" src="${esc(media(SHOWCASE.video))}"></video>`;
  }
  if (state.easy && state.easy.playedHere) {
    const vibe = (state.easy && state.easy.vibe) || "neon-night";
    const src = state.audioUrl || "/media/audio/demo";
    const clips = (window.XENO_CUT ? window.XENO_CUT.shots : ["wide", "medium", "close", "reveal"])
      .map(
        (shot, index) =>
          `<video class="cut-clip${index === 0 ? " on" : ""}" data-shot="${shot}" muted playsinline loop preload="auto" src="${esc(libraryClip(vibe, shot))}"></video>`,
      )
      .join("");
    return `<div class="screen" id="easy-screen" data-vibe="${esc(vibe)}" aria-label="Your cut">${clips}</div>
      <audio id="live-audio" src="${esc(media(src))}" preload="auto"></audio>`;
  }
  if (state.easy && state.easy.reopenUrl) {
    return `<video id="player" playsinline controls preload="auto" src="${esc(media(state.easy.reopenUrl))}"></video>`;
  }
  if (state.job && state.job.video) {
    return `<video id="player" playsinline preload="auto" src="${esc(media(state.job.video))}#t=0.5"></video>`;
  }
  return `<video id="player" playsinline poster="${media("/media/poster")}" src="${esc(media(state.video || "/media/demo"))}"></video>`;
}

function vibeCards(easy, compact, which) {
  const advanced = document.body.dataset.advanced === "1";
  const rows = VIBES.filter((vibe) => {
    if (which === "legacy") return !!vibe.legacy && vibe.id !== easy.vibe;
    return !vibe.legacy || vibe.id === easy.vibe || (advanced && which !== "featured");
  });
  return rows.map((vibe) => {
    const on = vibe.id === easy.vibe;
    const tone = vibe.tone || (vibe.dark ? "dark" : "bright");
    return `<button type="button" class="vibe-card${vibe.dark ? " is-dark" : ""}${on ? " on" : ""}${compact ? " is-mini" : ""}" role="radio" aria-checked="${on ? "true" : "false"}" tabindex="${on || (!easy.vibe && vibe.id === VIBES[0].id) ? "0" : "-1"}" data-act="easy-vibe" data-vibe="${esc(vibe.id)}">
      <span class="vibe-thumb" style="background-image:url(${esc(media(vibe.still))})"></span>
      ${on && !compact ? '<span class="vibe-tick" aria-hidden="true">✓</span>' : ""}
      <span class="vibe-meta"><strong>${esc(vibe.name)}</strong>${compact ? "" : `<em>${esc(tone)}</em>`}</span>
    </button>`;
  }).join("");
}

// The originals and the non-featured registry vibes, behind one drawer in Simple (Advanced lists them in the grid).
function moreVibes(easy) {
  const legacy = VIBES.filter((vibe) => vibe.legacy && vibe.id !== easy.vibe);
  if (!legacy.length || document.body.dataset.advanced === "1") return "";
  const open = readDrawer("xeno-more-vibes");
  return `<details class="more-vibes" id="more-vibes"${open ? " open" : ""}>
      <summary>More vibes <small>${legacy.length} more, the originals and the rest of the registry</small></summary>
      <div class="vibe-grid vibe-more" role="radiogroup" aria-label="More vibes">${vibeCards(easy, false, "legacy")}</div>
    </details>`;
}

function readDrawer(key) {
  try {
    return localStorage.getItem(key) === "1";
  } catch (err) {
    return false;
  }
}

function shotStrip(vibeId) {
  const shots = ["wide", "medium", "close", "reveal"];
  return shots
    .map((shot) => `<span class="strip-shot" style="background-image:url(${esc(libraryStill(vibeId, shot))})"></span>`)
    .join("");
}

function dropCard() {
  const opener = state.opener;
  const ready = opener && opener.ready;
  // Simple mode: plain words, not the library ids of the morph pair.
  const noDrop = opener && !ready && opener.line;
  const pair = ready
    ? `The big moment is at ${clockText(Number(opener.at || 0))}`
    : (noDrop ? "No big drop in this song" : "Listening for the drop.");
  const line = ready
    ? "That is where the biggest change happens: one object turns into the next, right on the downbeat."
    : (noDrop ? "The video still morphs on the beat. It just has no single big moment." : "The song decides the moment. This lands before any GPU wait.");
  return `<section class="drop-open" id="drop-open">
    <p class="eyebrow">The drop</p>
    <h3>${esc(pair)}</h3>
    <p class="drop-line">${esc(line)}</p>
    <button type="button" class="ghost" data-act="open-drop"${ready ? "" : " disabled"}>Play the drop</button>
  </section>`;
}

function renderEasy() {
  const easy = state.easy || { phase: "choose", song: "", vibe: "", idea: "", note: "" };
  const chosen = vibeById(easy.vibe) || VIBES[3];
  if (easy.phase === "making") {
    const width = Math.round(((state.job && state.job.progress) || 0.08) * 100);
    const scenes = state.scenes || [];
    const story = scenes.map((scene) => storySentence(scene.action)).filter(Boolean).slice(0, 2).join(" ") || easy.idea || chosen.line;
    const heard = easy.song ? "done" : "now";
    const wrote = scenes.length ? "done" : "now";
    const painting = scenes.length ? "now" : "wait";
    return `<div class="easy easy-making">
      <div class="easy-make-head">
        <div>
          <p class="eyebrow">${esc(chosen.name)} · ${esc(easy.songLabel || "Song")}</p>
          <h2>Making your video.</h2>
        </div>
        <div class="easy-make-actions">
          <span id="easy-eta" aria-live="polite">${esc(easyEtaText())}</span>
          <button type="button" class="ghost" data-act="easy-stop">Stop</button>
        </div>
      </div>
      <div class="easy-make-grid">
        <div>
          <div class="monitor" style="background-image:url(${esc(media(chosen.still))})">
            <span class="monitor-pill">${esc(scenes.length ? `Shot 1 of ${scenes.length}` : "Reading the song")}</span>
          </div>
          <div class="filmstrip">${shotStrip(chosen.id)}</div>
          <div class="track" aria-hidden="true"><span style="width:${width}%"></span></div>
        </div>
        <aside class="panel">
          <h3>What is happening</h3>
          <ol class="happen">
            <li class="${heard}">Listened to the song</li>
            <li class="${wrote}">Wrote the story</li>
            <li class="${painting}">Painting the shots</li>
            <li class="wait">Cutting to the beat</li>
          </ol>
          <p class="eyebrow">The story</p>
          <p>${esc(story)}</p>
          <p class="note" id="easy-progress">${esc(easy.note || "Reading the song.")}</p>
          <p class="note">You can leave this page. The video keeps going and waits for you.</p>
        </aside>
      </div>
    </div>`;
  }
  if (easy.phase === "result") {
    const title = easy.showcase ? "A finished one" : chosen && easy.vibe ? chosen.name : "Your cut";
    return `<div class="easy easy-done">
      <section class="easy-result">
        <div class="easy-result-head">
          <div>
            <p class="eyebrow">Your video</p>
            <h2>${esc(title)}</h2>
          </div>
          <div class="easy-result-actions">
            <button type="button" class="ghost" data-act="easy-share">Share cut</button>
            ${easyVideoId() ? '<button type="button" class="ghost" data-act="easy-hook" title="Cuts the strongest drop into a 15 second clip, same aspect and FX">15 s hook</button>' : ""}
            ${easyVideoId() ? '<button type="button" class="ghost" data-act="easy-copy-recipe">Copy recipe code</button>' : ""}
            <button type="button" class="generate" data-act="easy-download">Download</button>
          </div>
        </div>
        <div class="player">
          ${easyMedia()}
          <button type="button" class="play-toggle" data-act="easy-play" aria-label="Play">Play</button>
          <p class="ready-toast">Your video is ready.</p>
        </div>
        <p class="note" id="easy-note">${esc(easy.note || "")}</p>
        ${easy.hookUrl ? `<p class="note">15 s hook ready: <a href="${esc(media(easy.hookUrl))}" download>download the hook</a>${easy.hookInfo ? ` · ${esc(easy.hookInfo)}` : ""}</p>` : ""}
        ${easy.recipe ? `<p class="note recipe-line">Recipe <code>${esc(easy.recipe)}</code></p>` : ""}
      </section>
      <aside class="panel easy-side">
        <div class="energy-head"><h3>Energy</h3><b id="energy-readout">${esc(energyWord(state.energy || 0))}</b></div>
        <p class="note">Re-cuts the same shots instantly. No new pictures.</p>
        <input id="energy" type="range" min="0" max="1" step="0.01" value="${Number(state.energy || 0)}" aria-label="Energy from Calm to Hype" />
        <div class="energy-ends"><span>Calm</span><span>Hype</span></div>
        <div class="energy-head"><h3>Knobs</h3><span>Turn, then re-cut. No GPU.</span></div>
        <div class="simple-knobs"></div>
        ${lookRow(easy.danceFx || "auto", "easy-look")}
        <button type="button" class="generate easy-row" data-act="easy-recut-knobs"${easy.showcase || !easyVideoId() ? " disabled" : ""}>Re-cut with these knobs</button>
        <p class="note">Re-composes the same morphs with the knobs, the look and the orbit as they are now. No GPU, no new pictures: a fraction of the render time.</p>
        <div class="energy-head"><h3>Try another vibe</h3><span>Same song, same story</span></div>
        <div class="vibe-grid vibe-mini" role="radiogroup" aria-label="Try another vibe">${vibeCards(easy, true)}</div>
        ${easy.cloudPlan ? cloudCard(easy.cloudPlan) : ""}
        <button type="button" class="ghost easy-row" data-act="easy-better">Make it better</button>
        <button type="button" class="text easy-row" data-act="easy-advanced">Open in Advanced</button>
        <button type="button" class="text easy-row" data-act="easy-again">Back to the song</button>
      </aside>
    </div>`;
  }
  const preview = easy.vibe ? chosen : VIBES[3];
  const songSet = !!easy.song;
  const songBlock = songSet
    ? `<div class="songrow">
        <span class="play-dot" aria-hidden="true">▶</span>
        <div><strong>${esc(easy.songLabel || "Chosen")}</strong><span>${esc(songFacts() || "Ready")}</span></div>
        ${waveBars()}
      </div>`
    : `<div class="easy-actions">
        <label class="upload solid">Choose a song<input id="easy-file" type="file" accept="audio/*,.wav,.mp3,.flac,.ogg" aria-label="Choose a song" /></label>
        <button type="button" class="ghost${easy.song === "demo" ? " on" : ""}" data-act="easy-demo">Bundled demo</button>
      </div>`;
  return `<div class="easy easy-desk">
    <header class="easy-intro">
      <p class="eyebrow">Xenoform · Simple</p>
      <h2>Make a music video.</h2>
      <p class="lede">One object keeps transforming into the next, every change on the beat. A song, a vibe, Make. Free, local, open weights.</p>
      ${dropCard()}
    </header>
    <section class="easy-main">
      <section class="easy-step" data-tour="easy-song" data-song-drop="1">
        <div class="step-head"><h3>Song</h3>${songSet ? '<button type="button" class="text" data-act="easy-step" data-step="song">Change</button>' : ""}</div>
        ${songBlock}
        ${songSet ? "" : `<p class="note">${esc(easy.songLabel || "Drop a file here, or use the bundled demo.")}</p>`}
      </section>
      <section class="easy-step" data-tour="easy-vibe">
        <div class="step-head"><h3>Vibe</h3><span>Pick one. You can try another after.</span></div>
        <div class="vibe-grid" role="radiogroup" aria-label="Vibe">${vibeCards(easy, false, "featured")}</div>
        ${moreVibes(easy)}
        <label class="idea-field">Your idea in one line, if you have one.
          <input id="easy-idea" type="text" maxlength="170" value="${esc(easy.idea || "")}" aria-label="One line, optional" placeholder="Leave this empty and the vibe decides." autocomplete="off" />
        </label>
      </section>
      <section class="panel span simple-knobs-panel" data-tour="easy-macros">
        <h3>Knobs</h3>
        <p class="note">Intensity is the beat pulse and flash. Speed is the cut density and the trail length. Chaos is the punches, stutters and how far the subject swings. Glow is the bloom. The look rides the vibe's own colours unless you pick one.</p>
        <div class="simple-knobs"></div>
        ${lookRow(easy.danceFx || "auto", "easy-look")}
        <p class="note look-note">${esc(lookNote(easy.danceFx || "auto"))}</p>
      </section>
      ${galleryPanel()}
    </section>
    <aside class="panel easy-side" data-tour="easy-make">
      <div class="monitor" style="background-image:url(${esc(media(preview.still))})"><span class="monitor-pill">${esc(preview.name)} · sample</span></div>
      <div class="filmstrip">${shotStrip(preview.id)}</div>
      <dl class="facts">
        ${easyPlanFacts(easy)}
      </dl>
      <button type="button" class="generate easy-make" data-act="easy-make">Make my video</button>
      <p class="note house-line">9:16, Dense, Draft, Beat FX and the house look. Fine-tune only if you want to.</p>
      ${fineTune(easy)}
      ${easy.cloudPlan ? cloudCard(easy.cloudPlan) : ""}
      <p class="note"><a href="/moves">Moves: make a character dance to a real dance clip (Wan Animate 2) &rarr;</a></p>
      <p class="note"><a href="/vj">VJ mode: live visuals to this song's stems &rarr;</a> · <button type="button" class="text" data-act="easy-midi">MIDI controller</button></p>
      <button type="button" class="ghost easy-showcase" data-act="easy-showcase">Watch a finished one · plays now</button>
      <p class="note" id="easy-note">${esc(easy.note || "No ComfyUI? It plays in your browser.")}</p>
      <p class="side-foot"><a class="ow-badge" href="${esc(media("/licences"))}" title="LTX-2.3 has a revenue threshold. FLUX.2 Klein 9B is non-commercial. This desk uses the Apache 2.0 4B.">Open weights</a></p>
    </aside>
  </div>`;
}

// ---------------------------------------------------------------- Simple finishing (open weights)

function simpleSeg(act, current, choices, label) {
  const buttons = choices
    .map(([id, text]) => `<button type="button" class="${id === current ? "on" : ""}" data-act="${act}" data-value="${esc(id)}" aria-pressed="${id === current ? "true" : "false"}">${esc(text)}</button>`)
    .join("");
  return `<div class="simple-seg"><span>${esc(label)}</span><div class="toggle" role="group" aria-label="${esc(label)}">${buttons}</div></div>`;
}

function finalEtaText() {
  const info = state.simpleOptions && state.simpleOptions.final;
  if (!info) return "Final takes longer: minutes, not seconds.";
  const ready = info.ready ? "" : " Some Final files are missing on this machine, so it falls back to Draft.";
  const measured = info.eta_measured ? "" : " (estimate, not yet measured on this card)";
  return `Final: LTX-2.3 at ${info.render}, upscaled to ${info.output}. About ${clockText(info.eta_s)}${measured}.${ready}`;
}

// Fine-tune: everything that is not song / vibe / Make, in one drawer that remembers whether it was open.
function fineTune(easy) {
  const open = readDrawer("xeno-finetune");
  const bits = [easy.aspect || "9:16", (easy.energyPreset || "dense") === "dense" ? "Dense" : "Flow", (easy.tier || "draft") === "final" ? "Final" : "Draft",
    lookLabel(easy.danceFx || "auto")];
  return `<details class="fine-tune" id="fine-tune"${open ? " open" : ""}>
      <summary>Fine-tune <small>${esc(bits.join(" · "))}</small></summary>
      ${simpleOptions(easy)}
      ${ownRow(easy)}
      ${cloudToggles(easy)}
      ${remixBox(easy)}
    </details>`;
}

const LOOK_PRESETS = ["warm-leak", "cool-echo", "noir-glow", "bloom-rush", "negative-rush", "cyan-flash"];
const LOOK_NOTES = {
  "auto": "The vibe's own look when it has one, else the house VJ look (cool-echo).",
  "off": "No colour or light pass. The beat FX still cut on the beat.",
  "warm-leak": "warm split-tone grade, film halation on the bass and a corner light leak on the beat; no echo",
  "cool-echo": "cool blue grade, light ghost trail on 'other', cyan edge tint on the drums, frosted glass (the house VJ look)",
  "noir-glow": "high-contrast noir grade, violet edges, moderate halation and leak, a touch of glass",
  "bloom-rush": "hero / flower preset: long trails, heavy bloom, cyan-magenta gradient wash and chroma bleed (colour only)",
  "negative-rush": "bloom-rush plus a stem-driven negative: luma flips on the bass/beat with the hue kept, eased",
  "cyan-flash": "electric-blue beat flashes, negative pulse on big hits, slow light sweep, depth bloom and exposure breath",
};
function lookLabel(id) {
  if (id === "auto" || !id) return "Auto";
  if (id === "off") return "Off";
  const words = String(id).replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
function lookNote(id) {
  const served = (LOOKS || []).find((row) => row.id === id);
  return (served && served.note) || LOOK_NOTES[id] || "";
}
function lookRow(current, act, index) {
  const ids = ["auto", "off"].concat(LOOK_PRESETS);
  const chips = ids
    .map((id) => `<button type="button" class="chip${id === current ? " on" : ""}" data-act="${act}" data-value="${esc(id)}"${index == null ? "" : ` data-index="${index}"`} aria-pressed="${id === current ? "true" : "false"}" title="${esc(lookNote(id))}">${esc(lookLabel(id))}</button>`)
    .join("");
  return `<div class="simple-seg look-row"><span>Look</span><div class="toggle chips" role="group" aria-label="Look">${chips}</div></div>`;
}

// Where and on what it renders. Default: this machine, open weights. The GPU preset is detected; pick one to override.
// Performer shots: MiniMax H3 (open weights, local) has Polly sing and drum to the song in a few slots of the cut.
function performerRow(easy) {
  const info = (state.simpleOptions && state.simpleOptions.performer) || {};
  const ok = info.ok !== false;
  const n = Number(easy.performer || 0);
  const choices = [["0", "Off"], ["2", "2 shots"], ["4", "4 shots"]];
  const note = ok
    ? `MiniMax H3 (open weights, on this GPU) has Polly sing the intro and drum the drop, cut 1:1 into the morph chain. About ${clockText(Number(info.seconds_per_shot || 420))} a shot on a 12 GB card. The reference still is Polly; drop your own full-body still under Cast lock in Advanced to replace her.`
    : `Off: ${esc(info.note || "the MiniMax H3 files are not installed")}. See Setup.`;
  const styles = [["auto", "Auto"], ["sing", "Sing"], ["drums", "Drums"], ["keys", "Keys"], ["guitar", "Guitar"], ["dance", "Dance"]];
  const styleRow = n ? simpleSeg("easy-performer-style", easy.performerStyle || "auto", styles, "Performance") : "";
  const styleNote = n ? `<p class="note">Auto: she sings where the song's vocal stem sings (lip-synced to the vocal), drums on the drop, keys elsewhere; she never mouths words that are not there.</p>` : "";
  return `${simpleSeg("easy-performer", String(ok ? n : 0), choices, "Performer")}
      <p class="note">${note}</p>${styleRow}${styleNote}`;
}

// Your own clips and images: a folder on this machine, or files dropped or picked here. The images lead the
// vibe's morph chain (morph targets, in name order); each clip is cut in on the beat, one run of shots at the
// start of a passage (2 to 8 s), trimmed around its middle and played 1:1 like a performer shot.
function ownRow(easy) {
  const note = easy.ownNote || "Images lead the morphs, clips are cut in on the beat (one passage each, 2 to 8 s). Leave empty and the vibe's own objects carry the cut.";
  return `<div class="simple-seg own-row" data-own-drop><span>Your footage</span>
      <label class="ghost cloud-toggle">Folder <input type="text" id="easy-own-folder" value="${esc(easy.ownFolder || "")}" spellcheck="false" aria-label="Folder of your clips and images" placeholder="a folder of clips and images" style="width:16em"></label>
      <label class="ghost cloud-toggle">Drop or pick files <input type="file" multiple accept="video/*,image/*" data-act="easy-own-files" hidden></label>
      ${easy.ownId ? `<button type="button" class="ghost" data-act="easy-own-clear">Clear files</button>` : ""}
    </div>
    <p class="note">${esc(note)}</p>`;
}

function machineRows(easy) {
  const hw = (state.simpleOptions && state.simpleOptions.hardware) || {};
  const detected = hw.detected || {};
  const autoLabel = detected.label ? `Auto (${detected.label})` : "Auto";
  const tiers = [["auto", autoLabel]].concat((hw.tiers || [{id: "cpu", label: "CPU"}, {id: "8gb", label: "8 GB"}, {id: "12gb", label: "12 GB"}, {id: "24gb", label: "24 GB+"}]).map((t) => [t.id, t.label]));
  const endpoint = (state && state.endpoint) || "http://127.0.0.1:8188";
  const ok = state && state.comfyOk;
  const paidBox = document.getElementById("paid-cloud");
  const paidLocked = !!(paidBox && paidBox.disabled);
  return `${simpleSeg("easy-gpu", easy.gpuTier || "auto", tiers, "GPU")}
      <div class="simple-seg machine-where"><span>Renders on</span>
        <div class="toggle" role="group" aria-label="Renders on">
          <label class="ghost cloud-toggle">ComfyUI at <input type="text" id="easy-endpoint" value="${esc(endpoint)}" spellcheck="false" aria-label="ComfyUI address" style="width:13em"></label>
          <span class="note">${ok ? "connected" : "not connected"} · open weights on this machine</span>
        </div>
      </div>
      <label class="addon easy-paid"><input type="checkbox" data-act="easy-paid-cloud" ${state.paidCloud ? "checked" : ""}${paidLocked ? " disabled" : ""}> Paid cloud renders (LTX-2.5 partner node, Comfy Cloud account): off by default, not open weights${paidLocked ? " · locked off by XENO_PAID_CLOUD" : ""}</label>`;
}

function simpleOptions(easy) {
  const energy = easy.energyPreset || "dense";
  const aspect = easy.aspect || "9:16";
  const tier = easy.tier || "draft";
  const orbit = easy.stemOrbit !== false;
  const fx = easy.fx !== false;
  const card = !!easy.endCard;
  const vertical = tier === "final" ? (easy.vertical === "crop" ? "crop" : "native") : "crop";
  const vertNote = aspect !== "9:16" ? (aspect === "16:9" ? "" : " Each shot is reframed around the object as it changes.")
    : vertical === "native" ? " Native vertical: rendered in portrait (448×768), upscaled to 1080×1920, the object centred whole."
    : tier === "final" ? " Each shot is cropped from the 16:9 render around the object as it changes."
    : " Portrait Draft: every still re-laid whole on black, the morphs rendered in portrait (320×576) and composed at 540×960, so wide objects are never clipped.";
  return `<div class="simple-opts" data-tour="easy-options">
      ${simpleSeg("easy-energy", energy, [["flow", "Flow"], ["dense", "Dense"]], "Energy")}
      ${simpleSeg("easy-aspect", aspect, [["16:9", "16:9"], ["9:16", "9:16"], ["1:1", "1:1"]], "Aspect")}
      ${simpleSeg("easy-length", String(easy.lengthS || 0), [["0", "Full song"], ["60", "60 s"], ["30", "30 s"], ["15", "15 s"]], "Length")}
      <p class="note">${esc(lengthNote(easy))}</p>
      ${simpleSeg("easy-tier", tier, [["draft", "Draft · LTX-Video 0.9.5"], ["final", "Final · LTX-2.3 22B"]], "Model")}
      ${performerRow(easy)}
      ${machineRows(easy)}
      ${aspect === "9:16" && tier === "final" ? simpleSeg("easy-vertical", vertical, [["native", "Native"], ["crop", "Crop"]], "Vertical") : ""}
      ${morphControl(easy, tier, aspect, vertical)}
      ${simpleSeg("easy-fx", fx ? "on" : "off", [["on", "On"], ["off", "Off"]], "Beat FX")}
      ${simpleSeg("easy-orbit", orbit ? "on" : "off", [["on", "On"], ["off", "Off"]], "Subject orbit")}
      ${simpleSeg("easy-card", card ? "on" : "off", [["off", "Off"], ["on", "On"]], "End card")}
      <p class="note">${esc(energy === "dense" ? "Dense: a shot a bar, then a shot every half bar from the drop, with stutters, holds and punches. A long song loops a chain of up to 30 morphs, so every handoff stays one continuous transformation." : "Flow: one morph per section, cut on the bar.")}
      ${esc(vertNote)}
      ${esc(tier === "final" ? " " + finalEtaText() : " Draft: LTX 0.9.5, the quick pass.")}
      ${esc(easy.overlay ? "" : " Clean export: no waveform or text on the picture.")}</p>
    </div>`;
}

// Morph count: Auto (from clip length + BPM) or a fixed number of forms, with a time/VRAM estimate.
const MORPH_COST = {draft: {s: 35, vram_gb: 7.5}, final: {s: 110, vram_gb: 11.2}, final_916: {s: 140, vram_gb: 11.4}};
function autoMorphs(energy) {
  const m = state.simpleOptions && state.simpleOptions.morphs;
  if (m && m.auto) return m.auto;
  const secs = easySongSeconds() || 20;
  const bar = 4 * 60 / (Number(state.tempo) || 120);
  return Math.max(1, Math.round(secs / (energy === "dense" ? bar / 2 : Math.max(bar * 2, 4))));
}
function morphEstimate(count, tier, aspect, vertical) {
  const key = tier === "final" && aspect === "9:16" && vertical === "native" ? "final_916" : (tier === "final" ? "final" : "draft");
  const c = MORPH_COST[key];
  const secs = c.s * count + 20;
  return `about ${clockText(secs)}, peak VRAM ~${c.vram_gb} GB`;
}
function morphControl(easy, tier, aspect, vertical) {
  const auto = !easy.morphs || easy.morphs === "auto";
  const n = auto ? autoMorphs(easy.energyPreset || "dense") : Number(easy.morphs);
  return `<div class="seg morph-count" data-tour="easy-morphs"><span class="seg-label">Forms</span>
      <button type="button" data-act="easy-morphs-auto" class="${auto ? "on" : ""}">Auto${auto ? ` (${n})` : ""}</button>
      <input type="range" min="1" max="40" step="1" value="${Math.min(40, n)}" data-act="easy-morphs" aria-label="Number of forms">
      <input type="number" min="1" max="120" step="1" value="${n}" data-act="easy-morphs" aria-label="Number of forms" style="width:4.5em">
      <span class="note">${esc(`${n} form${n === 1 ? "" : "s"}: ${morphEstimate(n, tier, aspect, vertical)}`)}</span>
      <span class="note guard-live">${esc(morphGuardText(n))}</span>
    </div>`;
}
// Live guardrail hint, mirroring configs/guardrails.json morph_density (15 sweet spot, 18 hard per 20 s).
function morphGuardText(n) {
  const secs = easySongSeconds() || 20;
  const cap = Math.max(1, Math.round(secs / 20 * 15));
  const hard = Math.max(cap, Math.round(secs / 20 * 18));
  const expert = localStorage.getItem("xeno-guard-expert") === "1";
  if (n > hard) return expert ? `Guardrail: ${n} forms in ${Math.round(secs)}s reads as laggy (Expert: kept)` : `Guardrail: ${n} forms in ${Math.round(secs)}s reads as laggy; renders as ${cap}`;
  if (n > cap) return `Guardrail: above the ~${cap}-form sweet spot for ${Math.round(secs)}s`;
  return "";
}

function remixBox(easy) {
  return `<details class="remix"${easy.remixOpen ? " open" : ""}>
      <summary>Paste a recipe code</summary>
      <label class="idea-field">Someone's recipe code (starts with xf1.)
        <input id="easy-recipe" type="text" spellcheck="false" autocomplete="off" value="${esc(easy.remixCode || "")}" aria-label="Recipe code" />
      </label>
      <button type="button" class="ghost" data-act="easy-remix">Use this recipe</button>
      <p class="note">Same vibe, energy, aspect, quality and seed. Use the same song to get the same film, or a different one to remix it.</p>
    </details>`;
}

function galleryPanel() {
  const rows = (state.videos || []).slice(0, 12);
  if (!rows.length) {
    return `<section class="panel span gallery" id="my-videos"><h3>My videos</h3><p class="note">Videos you make in Simple mode show up here, with their recipe codes.</p></section>`;
  }
  const cards = rows
    .map((row) => `<figure class="gallery-card" data-aspect="${esc(row.aspect)}">
        <video muted playsinline preload="metadata" loop src="${esc(media(row.url))}#t=1.5"></video>
        <figcaption><strong>${esc(row.song || row.vibe || row.id)}</strong>
          <span>${esc([row.vibe, row.energy, row.aspect, row.tier].filter(Boolean).join(" · "))}</span>
          <span class="mono">${esc(String(row.created || "").replace("T", " ").slice(0, 16))}</span>
          <span class="gallery-actions">
            <button type="button" class="text" data-act="video-open" data-id="${esc(row.id)}">Reopen</button>
            <button type="button" class="text" data-act="video-rerender" data-id="${esc(row.id)}"${row.recipe ? "" : " disabled"}>Re-render</button>
            <button type="button" class="text" data-act="video-copy" data-id="${esc(row.id)}"${row.recipe ? "" : " disabled"}>Copy recipe</button>
          </span>
        </figcaption>
      </figure>`)
    .join("");
  return `<section class="panel span gallery" id="my-videos"><h3>My videos</h3><div class="gallery-grid">${cards}</div></section>`;
}

async function loadVideos() {
  try {
    const res = await api("/api/videos");
    if (!res.ok) return;
    state.videos = (await res.json()).videos || [];
  } catch (err) {
    state.videos = state.videos || [];
  }
}

// Called once a song is in (after /api/analyze or /api/demo) and whenever a Fine-tune choice changes the plan.
async function loadSimpleOptions() {
  try {
    const easy = (state && state.easy) || {};
    const duration = Math.round(easySongSeconds());
    if (!duration) {
      state.simpleOptions = null;
      return;
    }
    const query = new URLSearchParams({
      duration: String(duration),
      energy: easy.energyPreset || "dense",
      tier: easy.tier || "draft",
      bpm: String(Math.round(Number(state.tempo) || 120)),
      aspect: easy.aspect || "9:16",
      vertical: easy.vertical || "native",
      morphs: String(easy.morphs || "auto"),
      length: String(easy.lengthS || 0),
      performer: String(easy.performer || 0),
    });
    const res = await api(`/api/simple/options?${query.toString()}`);
    if (res.ok) {
      state.simpleOptions = await res.json();
      if (state.simpleOptions && Array.isArray(state.simpleOptions.looks) && state.simpleOptions.looks.length) LOOKS = state.simpleOptions.looks;
    }
  } catch (err) {
    state.simpleOptions = null;
  }
}

function easyVideoId() {
  if (state.easy && state.easy.reopenId) return state.easy.reopenId;
  const job = state.job || {};
  return job.status === "done" && job.id ? job.id : "";
}

function applySimpleRecipe(recipe) {
  const easy = state.easy;
  if (recipe.vibe && vibeById(recipe.vibe)) easy.vibe = recipe.vibe;
  easy.idea = recipe.idea || easy.idea || "";
  easy.energyPreset = recipe.energy_preset || "dense";
  easy.aspect = recipe.aspect || "9:16";
  easy.tier = recipe.quality_tier || "draft";
  easy.vertical = recipe.vertical_mode || "";
  easy.morphs = recipe.morph_count || "auto";
  easy.fx = recipe.beat_fx !== false;
  easy.overlay = !!recipe.beat_overlay;
  easy.endCard = !!recipe.end_card;
  easy.danceFx = recipe.dance_fx || "auto";
  easy.lengthS = Number(recipe.length_s || 0);
  easy.performer = Number(recipe.performer || 0);
  easy.performerStyle = recipe.performer_style || "auto";
  easy.ownFolder = recipe.own_folder || "";
  easy.stemOrbit = recipe.stem_orbit !== false;
  easy.remixPlan = recipe.cut_plan || null;
  state.seed = recipe.seed || state.seed;
}

async function decodeSimpleRecipe(code) {
  const res = await api("/api/simple/recipe/decode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipe: code }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "That recipe code did not read.");
  return body;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    return false;
  }
}

async function easyHook() {
  const id = easyVideoId();
  if (!id) return;
  state.easy.note = "Finding the strongest drop and cutting 15 seconds around it.";
  render();
  try {
    const res = await api(`/api/videos/${id}/hook`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ length: 15 }) });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "The hook did not cut.");
    state.easy.hookUrl = body.url;
    state.easy.hookInfo = `${clockText(body.start)} to ${clockText(body.end)}, drop at ${clockText(body.drop)}`;
    state.easy.note = "";
  } catch (err) {
    state.easy.note = String(err.message || err);
  }
  render();
}

async function easyRecipeFor(id) {
  const row = (state.videos || []).find((item) => item.id === id);
  if (row && row.recipe) return row.recipe;
  await loadVideos();
  const again = (state.videos || []).find((item) => item.id === id);
  return again ? again.recipe : "";
}

// One set of figures, the same as the README. Morph pass on a 12 GB RTX 3080 Ti
// (LTX 0.9.5, 512x288, T5 on the CPU), a 12-20 s song, seven morphs:
//   warm                                   45-65 s  -> estimate 50 s
//   first run, GPU idle                    about 1 minute -> 50 + 10 s
//   ComfyUI just had another model loaded  about 2 minutes (the live countdown catches up)
// A song longer than 20 s adds about 1.75 s per extra second (more morphs).
const EASY_ETA_WARM_S = 50;
const EASY_ETA_SONG_BASE_S = 20;
const EASY_ETA_PER_SONG_S = 1.75;
const EASY_ETA_COLD_S = 10;
const EASY_ETA_GPU_S = EASY_ETA_WARM_S; // 20 s clip, warm
const EASY_ETA_BROWSER_S = 6;
let easyTimer = null;

function clockText(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function easySongSeconds() {
  const ends = (state.scenes || []).map((scene) => Number(scene.end || 0)).filter((t) => t > 0);
  return ends.length ? Math.max.apply(null, ends) : Number(state.duration || 20) || 20;
}

function easyEtaGuess() {
  const cold = state.easy && state.easy.warm ? 0 : EASY_ETA_COLD_S;
  const extra = Math.max(0, Math.min(easySongSeconds(), 60) - EASY_ETA_SONG_BASE_S);
  return Math.round(EASY_ETA_WARM_S + EASY_ETA_PER_SONG_S * extra + cold);
}

// Once morphs come back, the server says "Morph k of N": re-estimate from the real pace.
function easyEtaLive() {
  const easy = state.easy;
  const job = state.job || {};
  const hit = /Morph (\d+) of (\d+)/.exec(String(job.detail || ""));
  if (!hit) return Number(easy.eta || EASY_ETA_GPU_S);
  const done = Number(hit[1]);
  const total = Number(hit[2]);
  const now = (Date.now() - easy.startedAt) / 1000;
  if (!easy.firstMorph || done < easy.firstMorph.done) easy.firstMorph = { done, at: now };
  const span = done - easy.firstMorph.done;
  const pace = span > 0 ? (now - easy.firstMorph.at) / span : 4.5;
  return now + (total - done) * pace + 2;
}

function easyEtaText() {
  const easy = state && state.easy;
  if (!easy || !easy.startedAt) return "About half a minute";
  const elapsed = (Date.now() - easy.startedAt) / 1000;
  const eta = easyEtaLive();
  const left = eta - elapsed;
  const draft = state.job && state.job.video ? "Draft playing · " : "";
  return left > 2 ? `${draft}${clockText(elapsed)} · about ${clockText(left)} left` : `${draft}${clockText(elapsed)} · almost there`;
}

// The stage the server is really on ("7 morphs queued on the GPU", "Morph 3 of 7 · ...").
// The countdown beside Stop re-estimates from the real morph pace.
function easyProgressText(job) {
  const detail = String((job && job.detail) || "").trim();
  if (!detail || detail === "Starting") return "Starting the GPU pass.";
  return detail;
}

// Same basis as easyEtaGuess: about 1:00 on a first run with the GPU idle, about 0:50 warm.
// What this Make will do, from /api/simple/options (plan: shots, morphs, estimate) once a song is in.
function easyVideoSeconds(easy) {
  const secs = easySongSeconds();
  const len = Number((easy || state.easy || {}).lengthS || 0);
  return len && secs > len ? len : secs;
}
function lengthNote(easy) {
  const secs = easySongSeconds();
  const len = Number(easy.lengthS || 0);
  if (!len) return `The whole song (${clockText(secs)}). Shorter cuts are centred on the drop.`;
  return secs > len ? `${len} s around the drop, starting on a beat with short fades.` : `The song is already under ${len} s, so the whole song.`;
}
function easyPlanFacts(easy) {
  const plan = state.simpleOptions && state.simpleOptions.plan;
  const secs = easySongSeconds();
  const len = Number(easy.lengthS || 0);
  const dense = (easy.energyPreset || "dense") === "dense";
  const rows = [["Video", `${clockText(easyVideoSeconds(easy))}${len && secs > len ? " around the drop" : " (the whole song)"}`]];
  if (plan && plan.shots) {
    rows.push(["Shots", plan.reuse ? `${plan.shots} on the beat, over a loop of ${plan.morphs} morphs` : `${plan.shots} morphs on the beat`]);
  } else {
    rows.push(["Shots", dense ? "A shot a bar, a half bar after the drop" : "One per section"]);
  }
  rows.push(["Cut", dense ? "Every bar, every half bar on the drop" : "On the bar"]);
  if (plan && plan.performer) rows.push(["Performer", `${plan.performer} shots of Polly (MiniMax H3)`]);
  rows.push(["Time", easyTimeFact()]);
  return rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
}
function easyTimeFact() {
  if (state.comfyOk === false) return "Seconds, in the browser";
  const plan = state.simpleOptions && state.simpleOptions.plan;
  if (plan && plan.estimate && plan.estimate.seconds) {
    const e = plan.estimate;
    return `About ${clockText(e.seconds)} on this GPU (${clockText(e.gpu_seconds || 0)} morphs, ${clockText(e.look_seconds || 0)} look)`;
  }
  const guess = easyEtaGuess();
  return `About ${clockText(guess)}${state.easy && state.easy.warm ? "" : " (first run)"}`;
}

function storySentence(text) {
  const line = String(text || "").trim().replace(/\s+/g, " ");
  if (!line) return "";
  const capital = line.charAt(0).toUpperCase() + line.slice(1);
  return /[.!?]$/.test(capital) ? capital : `${capital}.`;
}

function tickEasy() {
  if (!state || !state.easy || state.easy.phase !== "making") {
    if (easyTimer) clearInterval(easyTimer);
    easyTimer = null;
    return;
  }
  const label = document.getElementById("easy-eta");
  if (label) label.textContent = easyEtaText();
  const bar = document.querySelector(".easy-making .track span");
  if (bar) {
    const elapsed = (Date.now() - state.easy.startedAt) / 1000;
    const guess = Math.min(0.95, elapsed / easyEtaLive());
    const real = Number((state.job && state.job.status === "running" && state.job.stage !== "restyle" && state.job.progress) || 0) * 0.15;
    bar.style.width = `${Math.round(Math.max(guess, real) * 100)}%`;
  }
}

function cloudToggles(easy) {
  const overlay = !!easy.overlay;
  const overlayButton = `<button type="button" class="ghost cloud-toggle${overlay ? " on" : ""}" data-act="easy-overlay" aria-pressed="${overlay ? "true" : "false"}">Beat overlay · ${overlay ? "on" : "off"}</button>`;
  if (!state.paidCloud) {
    // Paid cloud renders are opt-in (Settings). Off, the main flow shows only open-weights choices.
    return `<div class="cloud-opts">${overlayButton}</div>`;
  }
  const cloud = !!easy.cloud;
  return `<div class="cloud-opts">
      <button type="button" class="ghost cloud-toggle${cloud ? " on" : ""}" data-act="easy-cloud" aria-pressed="${cloud ? "true" : "false"}">Cloud quality · ${cloud ? "on" : "off"}</button>
      <button type="button" class="ghost cloud-toggle${overlay ? " on" : ""}" data-act="easy-overlay" aria-pressed="${overlay ? "true" : "false"}">Beat overlay · ${overlay ? "on" : "off"}</button>
      ${cloud ? `<label class="ghost cloud-toggle">Cut plan · ${easy.cutPlan ? `${(easy.cutPlan.shots || []).length} shots` : "auto (~5s on the beat)"}<input type="file" accept="application/json,.json" data-act="easy-cut-plan" hidden></label>${easy.cutPlan ? `<button type="button" class="ghost" data-act="easy-cut-clear">Clear cut plan</button>` : ""}` : ""}
      <p class="note">Paid cloud renders are on (Settings). Cloud quality renders the morphs with LTX-2.5 through a paid Comfy partner node, which is not open weights. You see the price and confirm it first. Off, everything stays on open weights on this machine.</p>
    </div>`;
}

function cloudCard(plan) {
  const est = plan.estimate || {};
  const money = `${Number(est.credits || 0).toFixed(0)} credits · US$${Number(est.usd || 0).toFixed(2)} · A$${Number(est.aud || 0).toFixed(2)}`;
  const blockers = [];
  if (est.over_cap) blockers.push(`Over the US$${Number(est.cap_usd || 0).toFixed(2)} cap for one clip.`);
  if (!plan.node_installed) blockers.push("The LTX-2.5 partner node is not in this ComfyUI.");
  if (!plan.key_present && !plan.dry_run) blockers.push("No Comfy API key on this machine (COMFY_ORG_API_KEY).");
  const shots = (plan.shots || []).map((shot) => `${Number(shot.seconds).toFixed(2)}s←${shot.render_s}s${shot.speed ? ` @${Number(shot.speed).toFixed(2)}x` : ""}${(shot.effects || []).length ? "*" : ""}`).join(" · ");
  const go = plan.can_submit
    ? `<button type="button" class="generate" data-act="easy-cloud-confirm">${plan.dry_run ? "Dry run · spend nothing" : `Confirm and render · US$${Number(est.usd || 0).toFixed(2)}`}</button>`
    : "";
  return `<section class="cloud-card" role="dialog" aria-label="Cloud quality price">
      <h3>Cloud quality price</h3>
      <p><strong>${esc(money)}</strong></p>
      <p class="note">${esc(`${est.shots} LTX-2.5 shots, ${est.render_seconds}s at ${est.resolution} ${est.fps} fps, ${est.model}. Cap US$${Number(est.cap_usd || 0).toFixed(2)} a clip.`)}</p>
      <p class="note">${esc(shots)}</p>
      ${plan.custom_cut ? `<p class="note">Custom cut plan: you pay only for render seconds; speed, stutters and punches (*) are free post-processing.</p>` : ""}
      <p class="note">A free local draft plays while the cloud renders. If the cloud fails you keep the local cut. The result is labelled ${esc(plan.label || "cloud-rendered")}.</p>
      ${blockers.map((line) => `<p class="note warn">${esc(line)}</p>`).join("")}
      <div class="review-actions">
        <button type="button" class="ghost" data-act="easy-cloud-cancel">Use the free local engine</button>
        ${go}
      </div>
    </section>`;
}

async function easyCloudEstimate() {
  const vibe = vibeById(state.easy.vibe);
  state.easy.note = "Pricing the cloud shots. Nothing is sent yet.";
  render();
  try {
    const res = await api("/api/cloud/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio_id: state.audioId || "demo", vibe: vibe ? vibe.id : "", palette: vibe ? vibe.palette : "", brief: state.brief || "", cut_plan: state.easy.cutPlan || null, paid_cloud: !!state.paidCloud }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.easy.cloudPlan = await res.json();
    state.easy.note = "";
  } catch (err) {
    state.easy.cloudPlan = null;
    state.easy.cloud = false;
    state.easy.note = "Could not price the cloud shots, so Cloud quality is off.";
  }
  render();
}

// Re-cut the finished video from its cached morphs with the knobs / look / orbit as they are now (no GPU).
async function recutWithKnobs() {
  const id = easyVideoId();
  if (!id || !state.easy) return;
  const body = {
    macros: window.XENO_MACROS ? window.XENO_MACROS() : null,
    dance_fx: state.easy.danceFx || "auto",
    stem_orbit: state.easy.stemOrbit !== false,
    beat_fx: state.easy.fx !== false,
    end_card: !!state.easy.endCard,
  };
  try {
    const res = await api(`/api/jobs/${encodeURIComponent(id)}/recut`, body);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      state.easy.note = err.detail || "The re-cut did not start.";
      render();
      return;
    }
    state.job = Object.assign({}, state.job || {}, {id, status: "running", stage: "assemble", progress: 0.05, detail: "Re-cutting from the cached morphs"});
    state.easy.phase = "making";
    state.easy.recutting = true;
    render();
    poll(id);
  } catch (err) {
    state.easy.note = "The re-cut did not start.";
    render();
  }
}

async function easyMake() {
  const vibe = vibeById(state.easy.vibe);
  if (!vibe) return;
  if (!state.paidCloud) state.easy.cloud = false;
  if (state.easy.cloud && !state.easy.cloudToken) {
    await easyCloudEstimate();
    return;
  }
  state.easy.cloudPlan = null;
  state.easy.showcase = false;
  state.easy.reopenId = "";
  state.easy.reopenUrl = "";
  state.easy.hookUrl = "";
  state.easy.recipe = "";
  state.easy.startedAt = Date.now();
  state.easy.firstMorph = null;
  state.easy.eta = state.comfyOk === false ? EASY_ETA_BROWSER_S : easyEtaGuess();
  if (easyTimer) clearInterval(easyTimer);
  easyTimer = setInterval(tickEasy, 1000);
  state.easy.phase = "making";
  state.easy.note = "Reading the song. A few seconds.";
  state.brief = (state.easy.idea || "").trim() || vibe.line;
  state.palette = vibe.palette;
  state.register = vibe.register;
  state.morphCap = vibe.morph ? 1 : 0;
  state.energy = energyFromTrack();
  state.continuous = false;
  state.quality = "live";
  render();
  await planStory();
  if (!state || !state.easy || state.easy.phase !== "making") return;
  state.storyApproved = true;
  await refreshComfy();
  const blocked = state.logic && state.logic.ok === false;
  if (!state.comfyOk || blocked) {
    state.quality = "live";
    state.easy.phase = "result";
    state.easy.playedHere = true;
    state.easy.note = "Playing the pictures for this vibe.";
    render();
    return;
  }
  if (!state || !state.easy || state.easy.phase !== "making") return;
  state.quality = "turbo";
  state.testClips = ["0"];
  state.live = true;
  state.easy.playedHere = false;
  state.easy.note = "Cutting a preview, then the GPU pass.";
  const line = document.getElementById("easy-progress");
  if (line) line.textContent = state.easy.note;
  await generate();
  loadVideos().then(() => {
    const id = easyVideoId();
    const row = (state.videos || []).find((item) => item.id === id);
    if (row && state.easy) state.easy.recipe = row.recipe || "";
  });
  if (state.easy && state.easy.phase === "making" && state.job && state.job.status === "error") {
    state.quality = "live";
    state.easy.phase = "result";
    state.easy.playedHere = true;
    state.easy.note = "Playing the pictures for this vibe.";
    render();
  }
}

async function easyBetter() {
  await runReview();
  if (state.review && (state.review.findings || []).length) await applyReview(true);
  if (!state.easy) return;
  const reviewLine = String((state.review && state.review.summary) || "");
  state.easy.note = /live|board|gpu|ltx|seed|denoise|turbo|draft|final|comfy/i.test(reviewLine)
    ? "The cut is a little tighter."
    : plainWords(reviewLine) || "The cut is a little tighter.";
  render();
  if (state.quality === "live" && !(state.easy && state.easy.playedHere)) playLive();
}

function placeKey(node) {
  if (!node || node === document.body || node === document.documentElement) return "";
  if (node.id) return `#${node.id}`;
  if (!node.dataset || !node.dataset.act) return "";
  return ["act", node.dataset.act, node.dataset.vibe || "", node.dataset.index || "", node.dataset.quality || "", node.dataset.method || "", node.dataset.step || ""].join(":");
}

function rememberPlace() {
  const node = document.activeElement;
  const place = { y: window.scrollY || 0, key: placeKey(node), start: null, end: null };
  if (node && node.selectionStart != null) {
    place.start = node.selectionStart;
    place.end = node.selectionEnd;
  }
  return place;
}

function restorePlace(place) {
  if (!place || document.body.dataset.tour === "1") return;
  if (place.y) window.scrollTo(0, place.y);
  if (!place.key) return;
  let node = null;
  if (place.key.startsWith("#")) node = document.getElementById(place.key.slice(1));
  else {
    const parts = place.key.split(":");
    const act = parts[1];
    node = [...document.querySelectorAll(`[data-act="${act}"]`)].find((item) => {
      if (parts[2] && item.dataset.vibe !== parts[2]) return false;
      if (parts[3] && String(item.dataset.index || "") !== parts[3]) return false;
      if (parts[4] && item.dataset.quality !== parts[4]) return false;
      if (parts[5] && item.dataset.method !== parts[5]) return false;
      if (parts[6] && item.dataset.step !== parts[6]) return false;
      return true;
    });
  }
  if (!node || !node.focus) return;
  node.focus({ preventScroll: true });
  if (place.start != null && node.setSelectionRange) {
    try {
      node.setSelectionRange(place.start, place.end);
    } catch (error) {
      /* The control does not take a caret. */
    }
  }
}

function render() {
  const place = rememberPlace();
  const app = document.getElementById("app");
  state.view = viewFromHash();
  const advanced = document.body.dataset.advanced === "1";
  if (advanced) {
    state.step = deskStep();
    document.body.dataset.step = state.step;
    if (state.view === "scene") {
      if (state.expanded == null) state.expanded = state.climax == null ? 0 : state.climax;
    } else if (state.step !== "shots") {
      state.expanded = null;
    }
  } else {
    document.body.dataset.step = "";
    if (state.view === "scene") {
      if (state.expanded == null) state.expanded = state.climax == null ? 0 : state.climax;
    } else {
      state.expanded = null;
    }
  }
  document.body.dataset.mode = advanced ? "desk" : "easy";
  document.querySelectorAll(".views a").forEach((link) => {
    const current = state.view === "scene" ? "director" : state.view;
    if (link.dataset.view === current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const generate = document.getElementById("generate");
  generate.disabled = Boolean(state.job && state.job.status === "running");
  const view = advanced ? renderAdvanced() : renderEasy();
  app.innerHTML = view;
  paintRegisters();
  paintJob();
  paintReview();
  requestAnimationFrame(drawWave);
  mountLive();
  scheduleSession();
  document.body.dataset.ready = "1";
  if (document.getElementById("review-desk")) {
    document.querySelectorAll("#review-desk video").forEach((video) => {
      video.play().catch(() => {});
    });
    loadFrames();
  }
  if (window.XENO_IDEAS) window.XENO_IDEAS.mount();
  if (window.XENO_TUTORIAL) window.XENO_TUTORIAL.sync();
  paintGate();
  scheduleLibrary();
  scheduleScore();
  scheduleOpener();
  restorePlace(place);
}

function mountLive() {
  window.XENO_STATE = () => state;
  if (state && state.easy && state.easy.playedHere && document.getElementById("easy-screen")) {
    requestAnimationFrame(() => startLibraryCut());
    return;
  }
  if (!state || state.quality !== "live" || !window.XENO_LIVE) return;
  requestAnimationFrame(() => {
    if (state && state.quality === "live" && document.getElementById("live-canvas")) window.XENO_LIVE.mount();
  });
}

function startLibraryCut() {
  const screen = document.getElementById("easy-screen");
  const audio = document.getElementById("live-audio");
  if (!screen || !audio || !window.XENO_CUT || !state || !state.easy) return;
  const duration = Number(state.duration || 12);
  const beats = state.beats || [];
  const energy = Number(state.energy || 0);
  const windows = window.XENO_CUT.windows(duration, beats, energy);
  const drops = (state.sections || []).filter((section) => section.label === "drop").map((section) => Number(section.start) || 0);
  const morphs = window.XENO_CUT.morphs(windows, energy, drops);
  const clips = {};
  screen.querySelectorAll("video").forEach((node) => {
    clips[node.dataset.shot] = node;
  });
  const at = Number(state.easy.playAt || 0);
  function showAt(time) {
    if (!windows.length) return;
    let index = 0;
    for (let cursor = 0; cursor < windows.length; cursor += 1) {
      if (time >= windows[cursor][0]) index = cursor;
    }
    const shot = window.XENO_CUT.shot(index);
    const morph = morphs.indexOf(index) >= 0;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const into = windows[index] ? (time - windows[index][0]) / 0.4 : 1;
    const blending = morph && !reduced && into >= 0 && into < 1;
    window.XENO_CUT.shots.forEach((id) => {
      const node = clips[id];
      if (!node) return;
      const on = id === shot;
      node.classList.toggle("on", on);
      node.style.opacity = on && blending ? String(Math.max(0.15, into)) : "";
      if (on && node.paused) node.play().catch(() => {});
    });
    if (blending) {
      const previous = clips[window.XENO_CUT.shot(Math.max(0, index - 1))];
      if (previous) {
        previous.classList.add("on");
        previous.style.opacity = String(1 - into);
      }
    }
  }
  function arm() {
    if (at > 0 && audio.duration) audio.currentTime = Math.min(at, Math.max(0, audio.duration - 0.05));
    audio.play().catch(() => {});
    showAt(audio.currentTime || at || 0);
  }
  if (audio.readyState >= 1) arm();
  else audio.addEventListener("loadedmetadata", arm, { once: true });
  if (state.easy.cutFrame) cancelAnimationFrame(state.easy.cutFrame);
  function tick() {
    if (!document.getElementById("easy-screen")) return;
    showAt(audio.currentTime || 0);
    state.easy.cutFrame = requestAnimationFrame(tick);
  }
  state.easy.cutFrame = requestAnimationFrame(tick);
}

function paintGenerate() {
  const button = document.getElementById("generate");
  if (!button || !state) return;
  if (state.quality === "live") {
    button.disabled = false;
    button.classList.toggle("is-loading", Boolean(state.recording));
    button.textContent = state.recording ? "Stop" : "Record";
    return;
  }
  const running = Boolean(state.job && state.job.status === "running");
  button.disabled = false;
  button.classList.toggle("is-loading", running);
  button.textContent = running ? "Generating" : "Generate";
}

function kindLabel(kind) {
  if (kind === "rerender") return "Needs a picture";
  if (kind === "note") return "Note";
  return "Board fix";
}

function paintReview() {
  const slot = document.getElementById("reviewslot");
  if (!slot) return;
  const report = state && state.review;
  if (!report) {
    slot.innerHTML = "";
    return;
  }
  const findings = report.findings || [];
  const rows = findings.map((row) => {
    const change = row.before || row.after
      ? `<p class="ba"><span>${esc(row.before || "—")}</span> → <span>${esc(row.after || "—")}</span></p>`
      : "";
    return `<li>
      <span class="kind ${esc(row.kind || "cpu")}">${esc(kindLabel(row.kind))}</span>
      <strong>${esc(row.label || "Board")}</strong>
      <p>${esc(row.plain || "")}</p>
      ${change}
    </li>`;
  }).join("");
  const ranked = (report.ranked || [])
    .filter((row) => row.t != null || ["no-picture", "story-unclear", "loudness", "frame-one", "still-stretch", "cut-beat", "duration", "size", "fps", "clipping", "peak", "contrast", "margins", "harding"].includes(row.id))
    .map((row) => {
      const stamp = row.t == null ? "" : `<span class="when">${Number(row.t).toFixed(2)}s</span>`;
      return `<li><strong>${esc(row.id || "")}</strong> ${stamp}<p>${esc(row.plain || "")}</p></li>`;
    })
    .join("");
  const bar = (report.bar || [])
    .map((item) => {
      const mark = !item.measured ? "open" : item.pass ? "pass" : "fail";
      const word = !item.measured ? "open" : item.pass ? "pass" : "fail";
      return `<li class="${mark}"><span>${esc(word)}</span> ${esc(item.id || "")} <em>${esc(item.detail || "")}</em></li>`;
    })
    .join("");
  const verdict = report.verdict === "ship" ? "Ship" : report.verdict === "one more pass" ? "One more pass" : "";
  const retelling = report.retelling ? `<p class="retelling">${esc(report.retelling)}</p>` : "";
  const actionable = findings.some((row) => row.op && row.op.op);
  const apply = report.applied || !actionable
    ? ""
    : `<button type="button" class="generate${report.busy ? " is-loading" : ""}" data-act="apply-review" ${report.busy ? "disabled" : ""}>Apply all fixes</button>
       <button type="button" class="ghost${report.busy ? " is-loading" : ""}" data-act="fix-biggest" ${report.busy ? "disabled" : ""}>Fix the biggest</button>`;
  const undo = report.undo || state.reviewUndoId
    ? `<button type="button" class="ghost" data-act="undo-review">Undo</button>`
    : "";
  slot.innerHTML = `<section class="review" id="review-report">
    <p class="kicker">Review</p>
    <h2>${esc(report.summary || "Review")}</h2>
    ${verdict ? `<p class="verdict">${esc(verdict)}</p>` : ""}
    ${retelling}
    ${bar ? `<ul class="bar">${bar}</ul>` : ""}
    ${ranked ? `<p class="kicker">Fresh eyes</p><ol>${ranked}</ol>` : ""}
    ${rows ? `<ol>${rows}</ol>` : `<p class="note">Nothing on the board needs a change.</p>`}
    <div class="review-actions">${apply}${undo}<button type="button" class="text" data-act="dismiss-review">Dismiss</button></div>
  </section>`;
}

function reviewBody() {
  return {
    audio_id: state.audioId || "demo",
    quality: state.quality || "live",
    register: state.register || "pynchon",
    palette: state.palette || "violet",
    flash: state.flash || "normal",
    preset: state.preset || "",
    sliders: state.sliders || {},
    scenes: state.scenes || [],
    motif: state.motif || "",
    video: state.video || "",
    continuity: state.continuity || null,
  };
}

async function runReview() {
  if (!state || state.reviewBusy) return;
  state.reviewBusy = true;
  state.review = { summary: "Reading the board…", findings: [], busy: true };
  paintReview();
  const button = document.getElementById("review-fix");
  if (button) {
    button.disabled = true;
    button.classList.add("is-loading");
  }
  try {
    const response = await api("/api/v1/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reviewBody()),
    });
    const data = await response.json();
    if (!response.ok) {
      state.review = { summary: data.detail || "The review did not finish.", findings: [] };
    } else {
      state.review = data;
      if (data.ledger) state.ledger = data.ledger;
    }
  } catch (error) {
    state.review = { summary: "The review did not finish.", findings: [] };
  } finally {
    state.reviewBusy = false;
    if (button) {
      button.disabled = false;
      button.classList.remove("is-loading");
    }
    paintReview();
  }
}

async function applyReview(biggest = false) {
  const report = state.review;
  if (!report || report.busy || report.applied) return;
  state.reviewUndo = {
    scenes: JSON.parse(JSON.stringify(state.scenes || [])),
    flash: state.flash,
    sliders: { ...(state.sliders || {}) },
    preset: state.preset || "",
    blocks: JSON.parse(JSON.stringify(state.blocks || [])),
  };
  report.busy = true;
  report.summary = "Applying the fixes…";
  paintReview();
  const response = await api("/api/v1/review/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...reviewBody(), findings: report.findings || [], biggest: !!biggest }),
  });
  const data = await response.json();
  if (!response.ok) {
    report.busy = false;
    report.summary = data.detail || "Those fixes did not apply.";
    paintReview();
    return;
  }
  state.scenes = data.scenes || state.scenes;
  state.blocks = data.blocks || state.blocks;
  state.flash = data.flash || state.flash;
  state.sliders = data.sliders || state.sliders;
  state.preset = data.preset || "";
  state.reviewUndoId = data.undo || "";
  state.ledger = data.ledger || state.ledger;
  state.review = {
    summary: data.summary || "Fixes applied.",
    findings: data.findings || report.findings || [],
    ranked: report.ranked || [],
    bar: report.bar || [],
    verdict: report.verdict || "",
    retelling: report.retelling || "",
    applied: true,
    undo: data.undo || "",
  };
  if (data.job && data.job.id && state.quality !== "live") {
    state.job = {
      id: data.job.id,
      status: "running",
      progress: 0.02,
      detail: data.summary || "Queued",
      mode: "dry-run",
      quality: state.quality,
      only_scenes: data.rerender || [],
    };
    poll(data.job.id);
  }
  render();
}

async function undoReview() {
  const snapshot = state.reviewUndo;
  const versionId = state.reviewUndoId || (state.review && state.review.undo);
  if (versionId) {
    const response = await api("/api/v1/revert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version_id: versionId }),
    });
    if (response.ok) {
      const data = await response.json();
      if (data.scenes) state.scenes = data.scenes;
      if (data.blocks) state.blocks = data.blocks;
      if (data.flash) state.flash = data.flash;
      if (data.sliders) state.sliders = data.sliders;
    }
  }
  if (snapshot) {
    state.scenes = snapshot.scenes;
    state.flash = snapshot.flash;
    state.sliders = snapshot.sliders;
    state.preset = snapshot.preset;
    state.blocks = snapshot.blocks;
  }
  state.review = { summary: "Undone. The board is back where it was.", findings: [], applied: true };
  state.reviewUndo = null;
  state.reviewUndoId = "";
  render();
}

let sessionRevision = 0;
let skipPush = false;

function sessionBody() {
  return {
    source: "ui",
    audio_id: state.audioId,
    title: state.title,
    brief: state.brief || "",
    register: state.register,
    preset: state.preset || "",
    quality: state.quality,
    palette: state.palette,
    flash: state.flash,
    sliders: state.sliders,
    scenes: state.scenes,
    blocks: state.blocks,
    cards: state.cards,
    motif: state.motif || "",
    callback: state.callback || "",
    video: state.video || "",
    recipe: state.recipe || "",
  };
}

function scheduleSession() {
  if (skipPush) {
    skipPush = false;
    return;
  }
  clearTimeout(scheduleSession.timer);
  scheduleSession.timer = setTimeout(pushSession, 250);
}

async function pushSession() {
  if (!state) return;
  const response = await api("/api/v1/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sessionBody()),
  });
  if (!response.ok) return;
  const data = await response.json();
  if (data.revision) sessionRevision = data.revision;
}

function adoptAgent(data) {
  skipPush = true;
  sessionRevision = data.revision || sessionRevision;
  if (Array.isArray(data.scenes) && data.scenes.length) {
    state.scenes = data.scenes;
    state.board = data.scenes.map((scene) => ({ ...scene }));
  }
  if (Array.isArray(data.blocks) && data.blocks.length) state.blocks = data.blocks;
  if (data.register) state.register = data.register;
  if (data.palette) state.palette = data.palette;
  if (data.flash) state.flash = data.flash;
  if (data.quality) state.quality = data.quality;
  if (data.sliders && Object.keys(data.sliders).length) state.sliders = data.sliders;
  if (data.preset != null) state.preset = data.preset;
  if (data.brief != null) state.brief = data.brief;
  if (Array.isArray(data.cards) && data.cards.length) state.cards = data.cards;
  if (data.motif != null) state.motif = data.motif;
  if (data.callback != null) state.callback = data.callback;
}

async function pollAgent() {
  if (!state) return;
  const focused = document.activeElement && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
  if (focused) return;
  const response = await api("/api/v1/session");
  if (!response.ok) return;
  const data = await response.json();
  if (data.source === "agent" && Number(data.revision) > sessionRevision) {
    adoptAgent(data);
    render();
  }
}

async function testMcp() {
  const response = await api("/api/v1/mcp/status");
  state.mcp = response.ok ? await response.json() : { running: false, detail: "The desk did not answer." };
  if (state.view === "connect") render();
}

async function startMcp() {
  state.mcpBusy = true;
  if (state.view === "connect") render();
  const response = await api("/api/v1/mcp/start", { method: "POST" });
  state.mcp = response.ok ? await response.json() : { running: false, detail: "The agent port did not start." };
  if (state.view === "connect") render();
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    const status = await api("/api/v1/mcp/status");
    if (!status.ok) continue;
    state.mcp = await status.json();
    const node = document.getElementById("mcp-status");
    if (node && state.mcp) {
      node.textContent = state.mcp.detail || "";
      node.dataset.running = state.mcp.running ? "yes" : "no";
    }
    if (state.mcp.running) break;
  }
  state.mcpBusy = false;
  if (state.view === "connect") render();
}

function paintJob() {
  const slot = document.getElementById("jobslot");
  const job = state && state.job;
  paintGenerate();
  if (!job) {
    if (slot) slot.innerHTML = "";
    return;
  }
  if (!slot) return;
  const width = Math.round((job.progress || 0) * 100);
  const mode = job.mode === "live" ? "Live" : "Dry run";
  if (job.status === "cancelled") {
    slot.innerHTML = `<div class="jobbar"><strong>Stopped</strong><span>${esc(job.detail || "Cancelled. The card changed.")}</span></div>`;
    return;
  }
  if (job.status === "error") {
    slot.innerHTML = `<div class="jobbar error"><strong>Cut failed</strong><span>${esc(job.error || job.detail || "")}</span><button type="button" class="text" data-act="copy-job">Copy diagnostics</button></div>`;
    return;
  }
  const note = job.tier_note ? ` ${job.tier_note}` : "";
  const label = (job.status === "done" ? "Cut ready" : job.detail || "Working") + note;
  slot.innerHTML = `<div class="jobbar"><strong>${mode}</strong><span>${esc(label)}</span><div class="track"><span style="width:${width}%"></span></div></div>`;
  const guard = (job.guardrails && job.guardrails.messages) || [];
  if (guard.length) {
    slot.innerHTML += `<div class="guardnotes"><strong>Guardrails</strong><ul>${guard.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`;
  }
}

const SECTION_COLOR = {
  calm: "#eef0fb",
  build: "#e4e4e7",
  drop: "#f8d7cf",
  release: "#e5f0e8",
  sustain: "#f4f4f5",
};

function drawWave() {
  const canvas = document.getElementById("wave");
  if (!canvas || !state) return;
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 320;
  const height = canvas.clientHeight || 168;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#f4f4f5";
  ctx.fillRect(0, 0, width, height);
  const duration = state.duration || 1;
  for (const section of state.sections) {
    const x = (section.start / duration) * width;
    const w = ((section.end - section.start) / duration) * width;
    ctx.fillStyle = SECTION_COLOR[section.label] || "#e4e4e7";
    ctx.fillRect(x, 0, w, height);
  }
  for (const drop of state.drops) {
    const x = (drop.start / duration) * width;
    const w = Math.max(2, ((drop.end - drop.start) / duration) * width);
    ctx.fillStyle = "rgba(232, 81, 46, 0.85)";
    ctx.fillRect(x, 0, w, 8);
  }
  const peaks = state.waveform.length ? state.waveform : [0.2];
  ctx.beginPath();
  ctx.strokeStyle = "#2e2752";
  ctx.lineWidth = 1.25;
  peaks.forEach((peak, index) => {
    const x = (index / Math.max(peaks.length - 1, 1)) * width;
    const y = height * 0.86 - peak * (height * 0.68);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.strokeStyle = "#5560dd";
  ctx.lineWidth = 1;
  for (const beat of state.beats) {
    const x = (beat / duration) * width;
    ctx.beginPath();
    ctx.moveTo(x, height - 10);
    ctx.lineTo(x, height - 2);
    ctx.stroke();
  }
}

function scheduleRecipe() {
  clearTimeout(scheduleRecipe.timer);
  scheduleRecipe.timer = setTimeout(refreshRecipe, 160);
}

async function refreshRecipe() {
  if (!state) return;
  const response = await api("/api/recipe/encode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload()),
  });
  if (!response.ok) return;
  const data = await response.json();
  state.recipe = data.recipe;
  document.querySelectorAll("#recipe-out").forEach((node) => {
    node.textContent = data.recipe;
  });
}

function applyPreset(preset) {
  state.preset = preset.id;
  if (!state.locks.quality) state.quality = preset.quality;
  for (const key of Object.keys(preset.sliders)) {
    if (!state.locks[key]) state.sliders[key] = preset.sliders[key];
  }
}

let planTimer = 0;

async function planStory(extra = {}) {
  if (!state) return;
  const body = payload();
  if (extra.scenes) body.scenes = extra.scenes;
  if (extra.rolls) body.rolls = extra.rolls;
  if (extra.climax != null) body.climax = extra.climax;
  if (extra.treatment) body.treatment = extra.treatment;
  const response = await api("/api/story", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) return;
  const active = document.activeElement;
  const activeId = active && active.id;
  const caret = active && typeof active.selectionStart === "number" ? active.selectionStart : null;
  state.board = data.scenes;
  state.scenes = data.scenes;
  state.blocks = data.blocks;
  state.climax = data.climax;
  state.planner = data.planner;
  state.storyApproved = false;
  state.heldBoard = null;
  if (data.treatments) state.treatments = data.treatments;
  if (data.bible) state.bible = data.bible;
  if (data.treatment) state.treatment = data.treatment;
  if (data.continuity) state.continuity = data.continuity;
  if (data.logic) state.logic = data.logic;
  await settleCut({ full: true });
  if (activeId) {
    const next = document.getElementById(activeId);
    if (next) {
      next.focus();
      if (caret != null && next.setSelectionRange) next.setSelectionRange(caret, caret);
    }
  }
  scheduleRecipe();
}

function queuePlan(delay = 280) {
  clearTimeout(planTimer);
  planTimer = setTimeout(() => planStory(), delay);
}

let ignoreJob = null;

function cancelStale() {
  const job = state && state.job;
  if (!job || job.status !== "running" || !job.id) return;
  ignoreJob = job.id;
  state.job = Object.assign({}, job, { status: "cancelled", detail: "Cancelled. The card changed." });
  paintJob();
  api(`/api/jobs/${job.id}/cancel`, { method: "POST" }).catch(() => {});
}

function touchScene(index, key, value) {
  const scene = state.scenes[index];
  if (!scene) return;
  scene[key] = value;
  scene.edited = true;
  if (key === "bars") {
    const bar = Number(scene.bar_seconds) || 2;
    scene.hold = Math.round(Number(value) * bar * 100) / 100;
  }
  if (key === "edit" && (value === "hard cut" || value === "snap")) {
    scene.signature = false;
    scene.conditioning = "first-frame";
  }
  const source = state.board && state.board.length ? state.board[index % state.board.length] : null;
  if (source && source !== scene) {
    source[key] = value;
    source.edited = true;
  }
  if (key === "action" || key === "shot" || key === "move" || key === "mood" || key === "verb" || key === "protagonist" || key === "edit") {
    const shotWord = { wide: "Wide shot", medium: "Medium shot", close: "Close shot", reveal: "Reveal", macro: "Macro shot", overhead: "Overhead shot", tracking: "Tracking shot" }[scene.shot] || "Wide shot";
    const who = scene.protagonist || "the subject";
    const verb = scene.verb || "moves";
    if (scene.signature) {
      scene.guide = `Signature transition. ${shotWord} of ${who}. Action: ${verb}. ${scene.action}. Camera ${scene.move}. ${scene.mood} light.`;
    } else {
      scene.guide = `First frame only. ${shotWord} of ${who}. Action: ${verb}. ${scene.action}. Camera ${scene.move}. Hard cut on the bar. ${scene.mood} light.`;
    }
  }
  cancelStale();
  scheduleRecipe();
}

function randomise() {
  if (state.locks.script) {
    const hint = document.getElementById("recipe-hint");
    if (hint) hint.textContent = "The storyboard is locked.";
    return;
  }
  planStory({ rolls: 6, scenes: [] });
}

async function copyRecipe() {
  const hint = document.getElementById("recipe-hint");
  try {
    await navigator.clipboard.writeText(state.recipe);
    if (hint) hint.textContent = "Copied.";
  } catch {
    if (hint) hint.textContent = state.recipe;
  }
}

async function restoreRecipe() {
  const input = document.getElementById("recipe-in");
  const hint = document.getElementById("recipe-hint");
  const recipe = (input && input.value.trim()) || "";
  if (!recipe) {
    if (hint) hint.textContent = "Paste a code first.";
    return;
  }
  const response = await api("/api/recipe/decode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipe }),
  });
  const data = await response.json();
  if (!response.ok) {
    if (hint) hint.textContent = data.detail || "That code did not restore.";
    return;
  }
  state.preset = data.preset;
  state.quality = data.quality;
  state.sliders = data.sliders;
  state.locks = data.locks;
  state.blocks = data.blocks;
  state.register = data.register || "";
  state.palette = data.palette || "neutral";
  state.flash = data.flash || "normal";
  state.cards = data.cards || [];
  state.brief = data.brief || "";
  state.scenes = data.scenes || state.scenes;
  state.motif = data.motif || "";
  state.callback = data.callback || "";
  state.climax = data.climax;
  state.customs = (data.customs || []).map((form) => ({
    ...form,
    svg: "",
    blurb: form.blurb,
  }));
  state.recipe = data.recipe;
  state.selected = 0;
  if (hint) hint.textContent = "Restored.";
  render();
}

async function addNoun() {
  const input = document.getElementById("noun");
  const noun = (input && input.value.trim()) || "";
  if (!noun) return;
  const id = `c${state.customs.length}`;
  state.customs.push({
    id,
    noun,
    name: noun,
    kind: "noun",
    blurb: "Named on this desk.",
    accent: "#e7d7c3",
  });
  if (state.register === "custom" && !state.locks.script) state.blocks = customScript();
  else if (state.blocks[state.selected]) state.blocks[state.selected].form = id;
  render();
  scheduleRecipe();
}

async function uploadForm(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await api("/api/forms", { method: "POST", body });
  const data = await response.json();
  if (!response.ok) {
    window.alert(data.detail || "That picture did not attach.");
    return;
  }
  state.customs.push(data);
  if (state.register === "custom" && !state.locks.script) state.blocks = customScript();
  else if (state.blocks[state.selected]) state.blocks[state.selected].form = data.id;
  render();
  scheduleRecipe();
}

async function useDemoSong() {
  const note = document.getElementById("song-note");
  if (note) note.textContent = "Using the bundled demo, examples/demo.wav.";
  if (state && state.easy && document.body.dataset.advanced !== "1") {
    state.easy.song = "demo";
    state.easy.songLabel = "Bundled demo";
    state.easy.note = "";
    if (!state.easy.phase || state.easy.phase === "song" || state.easy.phase === "choose") state.easy.phase = "vibe";
  }
  if (!state || state.audioId === "demo") {
    if (document.body.dataset.advanced !== "1") render();
    return;
  }
  const response = await api("/api/demo");
  if (!response.ok) return;
  adoptSession(await response.json());
  await settleCut({ full: true });
  loadSimpleOptions().then(() => render());
}

async function uploadSong(file) {
  if (state && state.easy) {
    state.easy.song = "file";
    state.easy.songLabel = file.name;
    state.easy.note = "";
    if (!state.easy.phase || state.easy.phase === "song" || state.easy.phase === "choose") state.easy.phase = "vibe";
  }
  const app = document.getElementById("app");
  app.innerHTML = `<p class="boot">Reading ${esc(file.name)}…</p>`;
  const body = new FormData();
  body.append("file", file);
  const response = await api("/api/analyze", { method: "POST", body });
  const data = await response.json();
  if (!response.ok) {
    app.innerHTML = `<div class="error-panel"><h2>That song did not open.</h2><p>${esc(data.detail || "Analysis failed.")}</p></div>`;
    document.body.dataset.ready = "1";
    return;
  }
  if (state && state.board && state.board.length) state.heldBoard = JSON.parse(JSON.stringify(state.board));
  adoptSession(data, { keepScript: state.locks.script, keepLook: state.locks.preset });
  await settleCut({ full: true });
  loadSimpleOptions().then(() => render());
}

function adoptSession(data, options = {}) {
  const previous = state;
  state = {
    view: viewFromHash(),
    audioId: data.audio_id,
    title: data.title,
    duration: data.duration,
    tempo: data.tempo,
    fps: data.fps,
    waveform: data.waveform,
    beats: data.beats,
    drops: data.drops,
    sections: data.sections,
    forms: data.forms.filter((form) => form.kind === "preset"),
    customs: options.keepScript && previous ? previous.customs : data.customs || [],
    presets: data.presets,
    transitions: data.transitions,
    blocks: options.keepScript && previous ? previous.blocks : data.blocks,
    selected: 0,
    sliders: options.keepLook && previous ? previous.sliders : data.sliders,
    locks: previous ? previous.locks : data.locks,
    quality: options.keepLook && previous ? previous.quality : data.quality || "live",
    etas: data.etas || (previous && previous.etas) || null,
    audioUrl: data.audio_url || (previous && previous.audioUrl) || "",
    drive: data.drive || null,
    liveAiRequested: previous ? !!previous.liveAiRequested : false,
    liveAiPresent: previous ? !!previous.liveAiPresent : false,
    interpolate: previous ? !!previous.interpolate : false,
    guideId: previous ? previous.guideId || "" : "",
    recording: previous ? !!previous.recording : false,
    takes: previous ? previous.takes || [] : [],
    testClips: previous ? previous.testClips || [] : [],
    onlyScenes: previous ? previous.onlyScenes || [] : [],
    textOnly: previous ? !!previous.textOnly : false,
    frameUrls: previous ? previous.frameUrls || {} : {},
    lyricOn: previous ? !!previous.lyricOn : false,
    lyricOffset: previous ? Number(previous.lyricOffset || 0.9) : 0.9,
    lyricWords: previous ? previous.lyricWords || [] : [],
    lyricNote: previous ? previous.lyricNote || "" : "",
    lyricDraft: previous ? previous.lyricDraft || "" : "",
    gateReason: "",
    continuity: null,
    continuityKey: "",
    logic: null,
    energy: previous ? Number(previous.energy || 0) : 0,
    continuous: previous ? !!previous.continuous : false,
    heroId: previous ? previous.heroId || "" : "",
    heroUrl: previous ? previous.heroUrl || "" : "",
    storyApproved: options.keepScript && previous ? !!previous.storyApproved : false,
    storyNudge: false,
    titleText: previous ? previous.titleText || "" : "",
    endText: previous ? previous.endText || "" : "",
    styleNote: previous ? previous.styleNote || "" : "",
    transitionNote: previous ? previous.transitionNote || "" : "",
    easy: previous && previous.easy
      ? previous.easy
      : { song: "", songLabel: "", vibe: "", idea: "", ownFolder: "", ownId: "", ownNote: "", phase: "song", note: "", playedHere: false,
          // the house (demo_house): 9:16 native, Dense, Draft, Beat FX, the house look, subject orbit, no end card
          energyPreset: "dense", aspect: "9:16", tier: "draft", fx: true, endCard: false, danceFx: "auto", stemOrbit: true },
    morphCap: previous && previous.morphCap != null ? previous.morphCap : null,
    heldBoard: previous ? previous.heldBoard : null,
    board: options.keepScript && previous && previous.board ? previous.board : (data.scenes || []).map((scene) => ({ ...scene })),
    qa: null,
    grid: null,
    story: null,
    preset: options.keepLook && previous ? previous.preset : data.preset,
    registers: data.registers || (previous && previous.registers) || [],
    scripts: data.scripts || {},
    register: options.keepScript && previous ? previous.register : data.register || "pynchon",
    palette: options.keepScript && previous ? previous.palette : data.palette || "violet",
    flash: options.keepScript && previous ? previous.flash : data.flash || "normal",
    cards: options.keepScript && previous ? previous.cards : data.cards || [],
    brief: options.keepScript && previous ? previous.brief : data.brief || "",
    scenes: options.keepScript && previous ? previous.scenes : data.scenes || [],
    motif: options.keepScript && previous ? previous.motif : data.motif || "",
    callback: options.keepScript && previous ? previous.callback : data.callback || "",
    climax: options.keepScript && previous ? previous.climax : data.climax,
    planner: data.planner || "template",
    treatments: options.keepScript && previous ? previous.treatments : data.treatments || [],
    bible: options.keepScript && previous ? previous.bible : data.bible || null,
    treatment: options.keepScript && previous ? previous.treatment : data.treatment || "",
    ledger: previous ? previous.ledger : [],
    ledgerMarkdown: previous ? previous.ledgerMarkdown : "",
    shots: data.shots || ["wide", "close", "macro", "overhead", "tracking"],
    moves: data.moves || ["push in", "pull back", "orbit", "follow", "hold"],
    edits: data.edits || ["dissolve", "hard cut", "continuous", "pour-harden", "droplet-burst", "ribbon", "snap", "grow-out"],
    moods: data.moods || ["dawn", "neon", "storm", "cold", "forge", "night", "marble", "void"],
    expanded: viewFromHash() === "scene" ? (data.climax == null ? 0 : data.climax) : null,
    step: previous && previous.step ? previous.step : "song",
    morphMethod: previous && previous.morphMethod ? previous.morphMethod : "keyframe-blend",
    morphFast: previous ? !!previous.morphFast : false,
    morphHit: previous && previous.morphHit != null ? previous.morphHit !== false : readMorphHit(),
    morphReport: previous ? previous.morphReport : null,
    sceneTransitions: options.keepScript && previous ? previous.sceneTransitions || [] : [],
    transitionCatalog: previous ? previous.transitionCatalog || [] : [],
    transitionRecommended: previous ? previous.transitionRecommended || {} : {},
    libraryFolder: previous && previous.libraryFolder != null ? previous.libraryFolder : readLibraryFolder(),
    excludeFaces: previous && previous.excludeFaces != null ? previous.excludeFaces : readExcludeFaces(),
    allowPdUs: previous && previous.allowPdUs != null ? !!previous.allowPdUs : readAllowPdUs(),
    libraryPins: previous && previous.libraryPins ? previous.libraryPins.slice() : readIdList("xeno-library-pins"),
    libraryBans: previous && previous.libraryBans ? previous.libraryBans.slice() : readIdList("xeno-library-bans"),
    libraryTag: previous ? previous.libraryTag || "" : "",
    libraryItems: previous ? previous.libraryItems : null,
    libraryPick: previous ? previous.libraryPick : null,
    libraryNote: previous ? previous.libraryNote || "" : "",
    score: previous ? previous.score || null : null,
    videoModel: previous && previous.videoModel ? previous.videoModel : readVideoModel(),
    live: previous ? previous.live : false,
    addons: previous && previous.addons != null ? !!previous.addons : readAddons(),
    paidCloudEnv: data.paid_cloud ? String(data.paid_cloud.env || "") : previous ? previous.paidCloudEnv || "" : "",
    paidCloud: paidCloudFor(data, previous),
    endpoint: data.endpoint || (previous && previous.endpoint) || "",
    recipe: data.recipe,
    opener: previous && previous.audioId === data.audio_id ? previous.opener || null : null,
    video: data.video || (previous && previous.video) || "",
    videoLabel: data.video ? data.video_label || "Reference base form" : "No picture yet",
    reference: data.reference || "",
    job: previous ? previous.job : null,
    note: previous ? previous.note : "",
    pending: previous ? previous.pending : null,
    suggestions: previous ? previous.suggestions : [],
    versions: previous ? previous.versions : [],
    versionId: previous ? previous.versionId : null,
    flipId: previous ? previous.flipId : null,
    notesOpen: viewFromHash() === "notes",
    noteStatus: previous ? previous.noteStatus : "",
    noteBusy: false,
    lessonOffer: previous ? previous.lessonOffer : null,
    savedLessons: previous ? previous.savedLessons : [],
  };
  if (!state.video && data.audio_id === "demo") {
    state.video = "/media/demo";
    state.videoLabel = "Reference base form";
  }
}

function showEasyPreview(url) {
  const monitor = document.querySelector(".easy-making .monitor");
  if (!monitor || !url) return;
  const src = media(url);
  let video = monitor.querySelector("video.easy-preview");
  if (!video) {
    video = document.createElement("video");
    video.className = "easy-preview";
    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.loop = true;
    monitor.prepend(video);
  }
  if (video.getAttribute("src") !== src) {
    video.src = src;
    video.play().catch(() => {});
  }
}

function watchJob(job) {
  if (!job || !job.video) return;
  const version = job.video_version || 0;
  if (version && version === state.videoVersion) return;
  state.videoVersion = version;
  state.video = job.video;
  state.previewUrl = "";
  state.previewNote = "";
  state.videoLabel = job.status === "done"
    ? (state.quality === "turbo" ? "Turbo animatic" : (job.mode === "live" ? "Live cut" : "Dry-run cut"))
    : (job.detail || "Preview");
  state.reference = job.status === "done" ? "This pass" : "Preview";
  const player = document.getElementById("player");
  if (player) {
    const next = media(job.video);
    if (player.getAttribute("src") !== next) player.src = next;
  }
  const caption = document.querySelector(".caption");
  if (caption) caption.innerHTML = `<b>${esc(qualityLabel(state.quality))}</b> · seed 2727 · ${esc(state.videoLabel)}`;
}

let cutTimer = 0;

function patchCut() {
  document.querySelectorAll(".shotlist").forEach((list) => {
    list.innerHTML = shotRows();
  });
  const sceneGrid = document.querySelector(".scene-grid");
  if (sceneGrid) sceneGrid.innerHTML = sceneCards();
  const beat = document.getElementById("beat-grid");
  if (beat) beat.innerHTML = beatGridInner();
  const report = document.getElementById("qa-panel");
  if (report) report.innerHTML = qaInner();
  const story = document.getElementById("story-body");
  if (story) story.innerHTML = storyInner();
  const gate = document.getElementById("story-gate");
  if (gate) gate.textContent = gateCopy();
  const approve = document.getElementById("approve-story");
  if (approve) approve.textContent = state.storyApproved ? "Approved" : "Approve shot list";
  if (window.XENO_TUTORIAL) window.XENO_TUTORIAL.reposition();
}

async function settleCut(options = {}) {
  if (!state) return;
  if (!state.board || !state.board.length) {
    if (options.full) render();
    return;
  }
  const token = (settleCut.token = (settleCut.token || 0) + 1);
  let data = null;
  try {
    const response = await api("/api/recut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_id: state.audioId || "demo",
        energy: Number(state.energy || 0),
        continuous: !!state.continuous,
        hero_image: state.heroUrl || "",
        flash: state.flash || "normal",
        brief: state.brief || "",
        quality: state.quality || "live",
        morph_cap: state.morphCap == null ? null : state.morphCap,
        scenes: state.board,
      }),
    });
    data = await response.json();
    if (!response.ok) data = null;
  } catch (error) {
    data = null;
  }
  if (token !== settleCut.token) return;
  if (data && data.scenes) {
    state.scenes = data.scenes;
    if (data.blocks) state.blocks = data.blocks;
    state.grid = data.grid;
    state.qa = data.qa;
    state.story = data.story;
    if (data.continuity) state.continuity = data.continuity;
    if (data.logic) state.logic = data.logic;
    scheduleRecipe();
    loadContinuity();
  }
  if (options.full || !document.getElementById("beat-grid")) render();
  else patchCut();
}

function queueCut(delay = 40) {
  clearTimeout(cutTimer);
  cutTimer = setTimeout(() => settleCut(), delay);
}

function forgetApproval() {
  state.storyApproved = false;
  const gate = document.getElementById("story-gate");
  if (gate) gate.textContent = gateCopy();
  const approve = document.getElementById("approve-story");
  if (approve) approve.textContent = "Approve shot list";
}

function parseLyricDraft(text) {
  const words = [];
  for (const line of String(text || "").split(/\n+/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 3) continue;
    const end = Number(parts.pop());
    const start = Number(parts.pop());
    const word = parts.join(" ");
    if (!word || !Number.isFinite(start) || !Number.isFinite(end)) continue;
    words.push({ word, start, end });
  }
  return words;
}

let lyricTimer = 0;

function queueLyrics() {
  clearTimeout(lyricTimer);
  lyricTimer = setTimeout(alignLyrics, 280);
}

async function alignLyrics() {
  if (!state || !state.lyricOn) return;
  const token = (alignLyrics.token = (alignLyrics.token || 0) + 1);
  let data = null;
  try {
    const response = await api("/api/timing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_id: state.audioId || "demo",
        lyrics: true,
        offset: Number(state.lyricOffset || 0.9),
        words: parseLyricDraft(state.lyricDraft),
      }),
    });
    data = await response.json();
    if (!response.ok) data = null;
  } catch (error) {
    data = null;
  }
  if (!state || token !== alignLyrics.token || !state.lyricOn) return;
  if (!data) return;
  state.lyricWords = data.lyrics || [];
  state.lyricNote = data.note || "";
  const line = document.querySelector("#timing-panel .lyric-line");
  const note = document.querySelector("#timing-panel .note");
  if (line) line.innerHTML = (state.lyricWords || []).map((word) => `<i>${esc(word.word)}</i>`).join(" ");
  if (note) note.textContent = `Off by default. Local open weights only. Whisper runs 0.3–1.5s early, so a correction offset moves the words later. ${state.lyricNote || ""}`;
}

async function remakeShot(index, fresh) {
  if (!state || !(state.scenes || [])[index]) return;
  const scene = state.scenes[index];
  const prompt = scene.prompt || scene.guide || scene.action || "";
  let takes = (state.takes || []).map((take) => ({ ...take }));
  if (fresh && !takes.some((take) => take.scene === index)) {
    takes.push({ id: `s${index}-2727`, scene: index, seed: 2727, prompt, picked: false, repeated: false });
  }
  const owned = takes.filter((take) => take.scene === index).map((take) => Number(take.seed));
  const seed = fresh ? Math.max(2727, ...owned, takeSeed(index)) + 1 : takeSeed(index);
  let data = null;
  try {
    const response = await api("/api/review/remake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene: index, seed, prompt, takes }),
    });
    data = await response.json();
    if (!response.ok) data = null;
  } catch (error) {
    data = null;
  }
  if (!data || !state) return;
  state.takes = data.takes || takes;
  state.onlyScenes = data.only_scenes || [`s${index}`];
  state.textOnly = data.text_only !== false;
  state.gateReason = "";
  const key = `${index}:${seed}`;
  const previous = (state.frameUrls || {})[key];
  if (previous && String(previous).startsWith("blob:")) URL.revokeObjectURL(previous);
  delete state.frameUrls[key];
  render();
}

function pickTake(index, seed) {
  if (!state) return;
  state.takes = (state.takes || []).map((take) => (
    take.scene === index ? { ...take, picked: Number(take.seed) === seed } : take
  ));
  render();
}

function toggleTestClip(index, on) {
  if (!state) return;
  const id = String(index);
  let clips = (state.testClips || []).filter((item) => item !== id);
  if (on) {
    clips.push(id);
    if (clips.length > 2) clips = clips.slice(-2);
  }
  state.testClips = clips;
  state.gateReason = "";
  const gate = document.getElementById("story-gate");
  if (gate) gate.textContent = gateCopy();
  document.querySelectorAll("[data-act='test-clip']").forEach((box) => {
    box.checked = state.testClips.includes(String(box.dataset.index));
  });
  paintGate();
}

async function loadFrames() {
  if (!state || !document.getElementById("review-desk")) return;
  const token = (loadFrames.token = (loadFrames.token || 0) + 1);
  const inflight = loadFrames.inflight || (loadFrames.inflight = new Set());
  const jobs = (state.scenes || []).map((scene, index) => {
    const seed = takeSeed(index);
    return {
      index,
      seed,
      shot: scene.shot || "wide",
      prompt: scene.prompt || scene.guide || scene.action || "",
      key: `${index}:${seed}`,
    };
  });
  await Promise.all(jobs.map(async (job) => {
    if ((state.frameUrls || {})[job.key] || inflight.has(job.key)) return;
    inflight.add(job.key);
    try {
      const response = await api("/api/review/frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed: job.seed, shot: job.shot, prompt: job.prompt, scene: job.index }),
      });
      if (!response.ok || token !== loadFrames.token || !state) return;
      const blob = await response.blob();
      if (token !== loadFrames.token || !state) return;
      const url = URL.createObjectURL(blob);
      state.frameUrls[job.key] = url;
      const shots = document.querySelectorAll("#review-desk .review-shot");
      const figure = shots[job.index] && shots[job.index].querySelector("figure");
      if (!figure) return;
      const img = document.createElement("img");
      img.alt = `Keyframe ${job.index + 1}`;
      img.src = url;
      const wait = figure.querySelector(".frame-wait");
      if (wait) wait.replaceWith(img);
      else {
        const existing = figure.querySelector("img");
        if (existing) existing.src = url;
      }
    } catch (error) {
      /* The keyframe placeholder stays until the next pass. */
    } finally {
      inflight.delete(job.key);
    }
  }));
}

async function loadContinuity() {
  if (!state || !state.continuity || !(state.continuity.elements || []).length) return;
  const key = (state.continuity.elements || []).map((element) => element.sentence || "").join("|");
  if (state.continuityKey === key && (state.continuity.elements || []).every((element) => element.url)) return;
  const token = (loadContinuity.token = (loadContinuity.token || 0) + 1);
  let data = null;
  try {
    const response = await api("/api/continuity/stills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ elements: state.continuity.elements, scenes: state.scenes || [] }),
    });
    data = await response.json();
    if (!response.ok) data = null;
  } catch (error) {
    data = null;
  }
  if (!state || token !== loadContinuity.token || !data) return;
  state.continuity = { ...(state.continuity || {}), elements: data.elements || [] };
  state.continuityKey = key;
  const byId = Object.fromEntries((data.elements || []).map((element) => [element.id, element]));
  for (const scene of state.scenes || []) {
    const ids = scene.element_ids || [];
    const prop = ids.map((id) => byId[id]).find((element) => element && element.kind === "prop");
    const chosen = prop || byId[ids[0]] || null;
    if (!chosen || !chosen.still_name) continue;
    scene.still_name = chosen.still_name;
    scene.reference_url = chosen.url || "";
    if (scene.guide_from !== "previous-last") scene.guide_from = "reference";
  }
  const card = document.getElementById("continuity-card");
  if (card) {
    const fresh = continuityInner();
    const holder = document.createElement("div");
    holder.innerHTML = fresh;
    const next = holder.firstElementChild;
    if (next) card.replaceWith(next);
  }
  if (window.XENO_TUTORIAL) window.XENO_TUTORIAL.reposition();
}

async function shareCut(button) {
  if (!state) return;
  // A reopened cut (My videos) has no live job record: its id is the job folder, so Download shares that file.
  const jobId = (state.job && state.job.id) || (state.easy && state.easy.reopenId) || "";
  const job = jobId ? `?job=${encodeURIComponent(jobId)}` : "";
  if (button) button.classList.add("is-loading");
  try {
    const response = await api(`/api/share${job}`);
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "xenoform-720.mp4";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } finally {
    if (button && button.isConnected) button.classList.remove("is-loading");
  }
}

function showGate(reason) {
  state.storyNudge = true;
  state.gateReason = reason || "";
  const gate = document.getElementById("story-gate");
  if (gate) gate.textContent = gateCopy();
  paintGate();
}

async function generate() {
  if (state.quality !== "live" && !state.storyApproved) {
    showGate("");
    return;
  }
  if (state.quality !== "live" && state.logic && state.logic.ok === false) {
    showGate(state.logic.detail || "The story has to hold in one line before a render.");
    return;
  }
  if (state.quality !== "live" && !state.textOnly) {
    const approved = state.testClips || [];
    if (approved.length < 1 || approved.length > 2) {
      showGate("Approve 1 or 2 test clips before the full batch.");
      return;
    }
  }
  if (state.job && state.job.status === "running" && state.job.id) {
    ignoreJob = state.job.id;
    api(`/api/jobs/${state.job.id}/cancel`, { method: "POST" }).catch(() => {});
  }
  state.job = {
    status: "running",
    stage: "analyze",
    progress: 0.02,
    detail: "Starting",
    mode: state.live ? "live" : "dry-run",
    quality: state.quality,
    error: null,
  };
  render();
  const response = await api("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload()),
  });
  const data = await response.json();
  if (!response.ok) {
    state.job = { status: "error", stage: "analyze", progress: 0, detail: data.detail || "Could not start", error: data.detail, mode: state.live ? "live" : "dry-run" };
    paintJob();
    return;
  }
  state.job.id = data.id;
  poll(data.id);
}

async function poll(id) {
  if (ignoreJob === id) return;
  const response = await api(`/api/jobs/${id}`);
  if (!response.ok || ignoreJob === id) return;
  const job = await response.json();
  if (ignoreJob === id) return;
  state.job = job;
  watchJob(job);
  if (document.body.dataset.advanced !== "1" && state.easy && state.easy.phase === "making") {
    if (job.video) showEasyPreview(job.video);
    if (job.status === "done") {
      state.easy.phase = "result";
      state.easy.playedHere = false;
      state.easy.warm = true;
      state.easy.note = String(job.detail || "").startsWith("The animatic is ready")
        ? job.detail
        : "Your cut is ready.";
      render();
      return;
    }
    if (job.status === "error" || job.status === "cancelled") {
      state.quality = "live";
      state.easy.phase = "result";
      state.easy.playedHere = true;
      state.easy.note = "Playing the pictures for this vibe.";
      render();
      return;
    }
    const line = document.getElementById("easy-progress");
    if (line) line.textContent = easyProgressText(job);
  }
  const stages = document.getElementById("stages");
  if (stages) stages.outerHTML = stagesHtml();
  paintJob();
  if (job.status === "running") setTimeout(() => poll(id), 400);
}

document.addEventListener("click", async (event) => {
  const el = event.target.closest("[data-act]");
  if (!el || !state) return;
  const act = el.dataset.act;
  if (act === "rail") {
    goRail(el.dataset.step || "song");
  } else if (act === "palette") {
    openPalette();
  } else if (act === "palette-run") {
    runPalette(paletteRows[Number(el.dataset.index)]);
  } else if (act === "register") {
    applyRegister(el.dataset.register, false);
    render();
    scheduleRecipe();
  } else if (act === "to-director") {
    location.hash = "director";
  } else if (act === "use-demo" || act === "easy-demo") {
    useDemoSong();
  } else if (act === "easy-vibe") {
    state.easy.vibe = el.dataset.vibe || "";
    state.easy.note = "";
    if (state.easy.phase === "result") {
      if (state.easy.playedHere) render();
      else easyMake();
      return;
    }
    render();
    const next = document.querySelector(`[data-act=easy-vibe][data-vibe="${state.easy.vibe}"]`);
    if (next) next.focus();
    else {
      const make = document.querySelector("[data-act=easy-make]");
      if (make) make.focus();
    }
  } else if (act === "easy-make") {
    if (!state.easy.song || !state.easy.vibe) {
      state.easy.note = state.easy.song ? "Pick a vibe." : "Choose a song.";
      const note = document.getElementById("easy-note");
      if (note) note.textContent = state.easy.note;
      return;
    }
    easyMake();
  } else if (act === "easy-cloud") {
    state.easy.cloud = !state.easy.cloud;
    state.easy.cloudToken = "";
    state.easy.cloudPlan = null;
    render();
  } else if (act === "easy-cut-clear") {
    state.easy.cutPlan = null;
    state.easy.cloudPlan = null;
    state.easy.cloudToken = "";
    render();
  } else if (act === "easy-own-clear") {
    state.easy.ownId = "";
    state.easy.ownNote = "";
    render();
  } else if (act === "easy-overlay") {
    state.easy.overlay = !state.easy.overlay;
    render();
  } else if (act === "easy-energy") {
    state.easy.energyPreset = el.dataset.value === "dense" ? "dense" : "flow";
    render();
    loadSimpleOptions().then(render);
  } else if (act === "easy-aspect") {
    state.easy.aspect = ["16:9", "9:16", "1:1"].includes(el.dataset.value) ? el.dataset.value : "9:16";
    render();
    loadSimpleOptions().then(render);
  } else if (act === "easy-performer-style") {
    state.easy.performerStyle = ["auto", "sing", "drums", "keys", "guitar", "dance"].includes(el.dataset.value) ? el.dataset.value : "auto";
    render();
  } else if (act === "easy-performer") {
    state.easy.performer = [0, 2, 4].includes(Number(el.dataset.value)) ? Number(el.dataset.value) : 0;
    render();
    loadSimpleOptions().then(render);
  } else if (act === "easy-gpu") {
    state.easy.gpuTier = ["auto", "cpu", "8gb", "12gb", "24gb"].includes(el.dataset.value) ? el.dataset.value : "auto";
    render();
  } else if (act === "easy-paid-cloud") {
    state.paidCloud = !!el.checked;
    writePaidCloud(state.paidCloud);
    if (!state.paidCloud && state.easy) state.easy.cloud = false;
    const box = document.getElementById("paid-cloud");
    if (box && !box.disabled) box.checked = state.paidCloud;
    render();
  } else if (act === "easy-length") {
    state.easy.lengthS = [0, 60, 30, 15].includes(Number(el.dataset.value)) ? Number(el.dataset.value) : 0;
    render();
    loadSimpleOptions().then(render);
  } else if (act === "easy-look") {
    state.easy.danceFx = el.dataset.value || "auto";
    render();
  } else if (act === "easy-orbit") {
    state.easy.stemOrbit = el.dataset.value !== "off";
    render();
  } else if (act === "easy-midi") {
    openMidiDrawer();
  } else if (act === "vj-open") {
    window.open(vjUrl(), "_blank", "noopener");
  } else if (act === "mcp-copy") {
    const line = connectSnippets().stdio;
    const ok = await copyText(line);
    const hint = document.getElementById("recipe-hint");
    if (hint) hint.textContent = ok ? "MCP connect line copied (Claude Desktop / Cursor mcpServers block)." : line;
  } else if (act === "scene-transition-reset") {
    state.sceneTransitions = [];
    render();
  } else if (act === "easy-morphs-auto") {
    state.easy.morphs = "auto";
    render();
  } else if (act === "easy-vertical") {
    state.easy.vertical = el.dataset.value === "crop" ? "crop" : "native";
    render();
  } else if (act === "easy-tier") {
    state.easy.tier = el.dataset.value === "final" ? "final" : "draft";
    render();
    loadSimpleOptions().then(render);
  } else if (act === "easy-fx") {
    state.easy.fx = el.dataset.value !== "off";
    render();
  } else if (act === "easy-card") {
    state.easy.endCard = el.dataset.value === "on";
    render();
  } else if (act === "easy-hook") {
    easyHook();
  } else if (act === "easy-copy-recipe") {
    const code = state.easy.recipe || (await easyRecipeFor(easyVideoId()));
    state.easy.recipe = code;
    state.easy.note = code && (await copyText(code)) ? "Recipe code copied." : code ? "Recipe code below." : "No recipe code for this cut.";
    render();
  } else if (act === "easy-remix") {
    const input = document.getElementById("easy-recipe");
    const code = input ? input.value.trim() : "";
    state.easy.remixCode = code;
    state.easy.remixOpen = true;
    try {
      applySimpleRecipe(await decodeSimpleRecipe(code));
      state.easy.note = state.easy.song ? "Recipe loaded. Make my video renders it." : "Recipe loaded. Choose a song, then Make.";
    } catch (err) {
      state.easy.note = String(err.message || err);
    }
    render();
  } else if (act === "video-open") {
    const row = (state.videos || []).find((item) => item.id === el.dataset.id);
    if (!row) return;
    state.easy.reopenId = row.id;
    if (row.vibe && vibeById(row.vibe)) state.easy.vibe = row.vibe;
    state.easy.reopenUrl = row.url;
    // Download / Share cut read the job id from here; a job record is not needed for a saved file.
    state.job = { id: row.id, status: "done", stage: "done", progress: 1, video: row.url, reopened: true };
    state.easy.recipe = row.recipe || "";
    state.easy.hookUrl = row.hook ? `/api/videos/${row.id}/hook.mp4` : "";
    state.easy.hookInfo = "";
    state.easy.showcase = false;
    state.easy.playedHere = false;
    state.easy.phase = "result";
    render();
  } else if (act === "video-copy") {
    const code = await easyRecipeFor(el.dataset.id);
    state.easy.note = code && (await copyText(code)) ? "Recipe code copied." : code ? `Recipe: ${code}` : "No recipe code for that video.";
    render();
  } else if (act === "video-rerender") {
    const code = await easyRecipeFor(el.dataset.id);
    if (!code) return;
    try {
      applySimpleRecipe(await decodeSimpleRecipe(code));
      if (!state.easy.song) {
        state.easy.note = "Recipe loaded. Choose the song again, then Make.";
        render();
        return;
      }
      easyMake();
    } catch (err) {
      state.easy.note = String(err.message || err);
      render();
    }
  } else if (act === "easy-cloud-confirm") {
    const plan = state.easy.cloudPlan;
    if (!plan || !plan.token || !plan.can_submit) return;
    state.easy.cloudToken = plan.token;
    state.easy.cloudPlan = null;
    easyMake().finally(() => {
      if (state.easy) state.easy.cloudToken = "";
    });
  } else if (act === "easy-cloud-cancel") {
    state.easy.cloud = false;
    state.easy.cloudToken = "";
    state.easy.cloudPlan = null;
    render();
  } else if (act === "easy-play") {
    if (state.easy && state.easy.playedHere) startLibraryCut();
    else {
      const player = document.getElementById("player");
      if (player && player.play) player.play().catch(() => {});
    }
  } else if (act === "easy-download") {
    if (state.easy && state.easy.showcase) {
      const link = document.createElement("a");
      link.href = media(SHOWCASE.video);
      link.download = "xenoform-showcase.mp4";
      document.body.appendChild(link);
      link.click();
      link.remove();
      return;
    }
    if (state.easy && state.easy.playedHere) {
      state.easy.note = "This cut is the pictures on screen. A file needs ComfyUI.";
      const note = document.getElementById("easy-note");
      if (note) note.textContent = state.easy.note;
      return;
    }
    shareCut(el);
  } else if (act === "easy-share") {
    if (state.easy && state.easy.playedHere) {
      state.easy.note = "This cut is the pictures on screen. A file needs ComfyUI.";
      const note = document.getElementById("easy-note");
      if (note) note.textContent = state.easy.note;
      return;
    }
    shareCut(el);
  } else if (act === "morph-fast") {
    state.morphFast = !state.morphFast;
    state.morphReport = null;
    render();
  } else if (act === "morph-hit") {
    state.morphHit = state.morphHit === false;
    writeMorphHit(state.morphHit);
    state.morphReport = null;
    render();
  } else if (act === "morph-method") {
    state.morphMethod = el.dataset.method || "keyframe-blend";
    state.morphReport = null;
    render();
  } else if (act === "library-pin") {
    const id = el.dataset.id || "";
    if (!id) return;
    const pins = state.libraryPins || [];
    state.libraryPins = pins.indexOf(id) >= 0 ? pins.filter((item) => item !== id) : pins.concat([id]);
    writeLibraryPrefs();
    state.libraryPick = null;
    scheduleLibrary();
  } else if (act === "score-rerender") {
    rerenderSection(Number(el.dataset.start), Number(el.dataset.end));
  } else if (act === "library-ban") {
    const id = el.dataset.id || "";
    if (!id) return;
    const bans = state.libraryBans || [];
    state.libraryBans = bans.indexOf(id) >= 0 ? bans.filter((item) => item !== id) : bans.concat([id]);
    writeLibraryPrefs();
    state.libraryPick = null;
    scheduleLibrary();
  } else if (act === "morph-check") {
    el.classList.add("is-loading");
    loadMorph().finally(() => {
      if (el.isConnected) el.classList.remove("is-loading");
    });
  } else if (act === "easy-step") {
    if (el.dataset.step === "song") {
      state.easy.song = "";
      state.easy.songLabel = "";
    }
    state.easy.phase = "choose";
    render();
  } else if (act === "easy-stop") {
    if (state.job && state.job.status === "running" && state.job.id) {
      ignoreJob = state.job.id;
      api(`/api/jobs/${state.job.id}/cancel`, { method: "POST" }).catch(() => {});
    }
    state.easy.phase = "choose";
    state.easy.note = "Stopped. Anything still queued on the GPU was cancelled.";
    render();
  } else if (act === "easy-showcase") {
    state.easy.showcase = true;
    state.easy.playedHere = false;
    state.easy.phase = "result";
    state.easy.note = "Made earlier on one RTX 3080 Ti with open weights: five LTX morphs, cut to the bar of our own track. Back to the song, then Make, cuts your own in about 1 minute on a 12 GB GPU (45-65 seconds once warm), with a live countdown.";
    render();
    const player = document.getElementById("player");
    if (player && player.play) player.play().catch(() => {});
  } else if (act === "easy-again") {
    state.easy.showcase = false;
    state.easy.phase = "choose";
    state.easy.note = "";
    render();
  } else if (act === "easy-recut-knobs") {
    recutWithKnobs();
  } else if (act === "easy-better") {
    el.classList.add("is-loading");
    easyBetter();
  } else if (act === "easy-advanced") {
    syncAdvanced(true);
    if (location.hash !== "#simple") location.hash = "simple";
    else render();
  } else if (act === "try-it") {
    el.classList.add("is-loading");
    tryDemo();
  } else if (act === "generate-inline") {
    el.classList.add("is-loading");
    if (state.quality === "live") playLive();
    else generate();
  } else if (act === "live-play") {
    playLive();
  } else if (act === "live-record") {
    recordToggle();
  } else if (act === "check-extra") {
    loadSetup().then(() => {
      if (state.view === "setup") render();
    });
  } else if (act === "download-model") {
    downloadModel(el.dataset.id);
  } else if (act === "copy-job") {
    copyText(state.job && state.job.diagnostics ? state.job.diagnostics : state.job && state.job.error);
  } else if (act === "expand") {
    state.expanded = Number(el.dataset.index);
    if (location.hash !== "#scene") location.hash = "scene";
    else render();
  } else if (act === "motif") {
    const scene = state.scenes[Number(el.dataset.index)];
    if (!scene) return;
    state.motif = state.motif === scene.form ? "" : scene.form;
    planStory({ scenes: [] });
  } else if (act === "lock") {
    state.locks[el.dataset.key] = !state.locks[el.dataset.key];
    render();
    scheduleRecipe();
  } else if (act === "quality") {
    if (!state.locks.quality && state.quality !== el.dataset.quality) {
      state.quality = el.dataset.quality;
      state.preset = state.locks.preset ? state.preset : "";
      cancelStale();
      render();
      scheduleRecipe();
      settleCut();
    }
  } else if (act === "assign") {
    if (state.blocks[state.selected]) state.blocks[state.selected].form = el.dataset.form;
    render();
    scheduleRecipe();
  } else if (act === "select-block") {
    if (event.target.closest("select, input")) return;
    state.selected = Number(el.dataset.index);
    render();
  } else if (act === "add-noun") {
    addNoun();
  } else if (act === "preset") {
    if (state.locks.preset) return;
    const preset = state.presets.find((item) => item.id === el.dataset.preset);
    if (preset) applyPreset(preset);
    render();
    scheduleRecipe();
  } else if (act === "random") {
    randomise();
    render();
    scheduleRecipe();
  } else if (act === "copy") {
    copyRecipe();
  } else if (act === "restore") {
    restoreRecipe();
  } else if (act === "apply-note") {
    interpretNote(true);
  } else if (act === "chip") {
    state.note = el.dataset.note || "";
    state.notesOpen = true;
    interpretNote(true);
  } else if (act === "confirm-note") {
    confirmNote();
  } else if (act === "undo-note") {
    state.pending = null;
    state.noteStatus = "Note set aside. The cut is unchanged.";
    render();
  } else if (act === "watch-version") {
    watchVersion(el.dataset.id);
  } else if (act === "revert-version") {
    revertVersion(el.dataset.id);
  } else if (act === "flip") {
    flipVersions();
  } else if (act === "save-lesson") {
    saveLesson();
  } else if (act === "dismiss-lesson") {
    state.lessonOffer = null;
    if (state.pending) state.pending.lesson_offer = null;
    render();
  } else if (act === "treatment") {
    el.classList.add("is-loading");
    el.disabled = true;
    state.treatment = el.dataset.treatment || "";
    planStory({ treatment: state.treatment }).finally(() => {
      if (el.isConnected) {
        el.classList.remove("is-loading");
        el.disabled = false;
      }
    });
  } else if (act === "approve-story") {
    state.storyApproved = true;
    state.storyNudge = false;
    state.gateReason = "";
    const gate = document.getElementById("story-gate");
    if (gate) gate.textContent = gateCopy();
    paintGate();
    if (el.id === "approve-story") el.textContent = "Approved";
  } else if (act === "conform") {
    el.classList.add("is-loading");
    conformStory().finally(() => {
      if (el.isConnected) el.classList.remove("is-loading");
    });
  } else if (act === "music-only") {
    const audioId = encodeURIComponent(state.audioId || "demo");
    window.location.href = `/api/v1/music?audio_id=${audioId}`;
  } else if (act === "open-drop") {
    openDrop();
  } else if (act === "preview") {
    previewAnimatic(el);
  } else if (act === "export-workflow") {
    exportWorkflow(el);
  } else if (act === "share-cut") {
    shareCut(el);
  } else if (act === "remake") {
    remakeShot(Number(el.dataset.index), false);
  } else if (act === "new-take") {
    remakeShot(Number(el.dataset.index), true);
  } else if (act === "pick-take") {
    pickTake(Number(el.dataset.index), Number(el.dataset.seed));
  } else if (act === "apply-review") {
    applyReview(false);
  } else if (act === "fix-biggest") {
    applyReview(true);
  } else if (act === "undo-review") {
    undoReview();
  } else if (act === "dismiss-review") {
    state.review = null;
    paintReview();
  } else if (act === "copy-snippet") {
    const node = document.getElementById(`snippet-${el.dataset.snippet}`);
    copyText(node ? node.textContent : "");
  } else if (act === "mcp-test") {
    testMcp();
  } else if (act === "mcp-start") {
    startMcp();
  }
});

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!state) return;
  if (target.id === "palette-q") {
    state.paletteAt = 0;
    paintPalette();
  } else if (target.id === "note-text") {
    state.note = target.value;
  } else if (target.id === "energy") {
    const playing = document.getElementById("live-audio");
    if (playing && state.easy) state.easy.playAt = playing.currentTime || 0;
    if (state.easy && state.easy.phase === "result") state.morphCap = null;
    state.energy = Number(target.value);
    const label = document.getElementById("energy-readout");
    if (label) label.textContent = energyWord(state.energy);
    forgetApproval();
    queueCut(40);
  } else if (target.id === "title-card") {
    state.titleText = target.value;
  } else if (target.id === "easy-idea") {
    state.easy.idea = target.value;
  } else if (target.id === "easy-own-folder") {
    state.easy.ownFolder = target.value;
    state.easy.ownId = "";  // one source at a time: a typed folder replaces dropped files
    state.easy.ownNote = "";
  } else if (target.id === "style-note") {
    state.styleNote = target.value;
  } else if (target.id === "transition-note") {
    state.transitionNote = target.value;
  } else if (target.id === "end-card") {
    state.endText = target.value;
  } else if (target.dataset.prompt != null) {
    const index = Number(target.dataset.prompt);
    const scene = state.scenes[index];
    if (!scene) return;
    scene.prompt = target.value;
    scene.guide = target.value;
    state.textOnly = true;
    state.onlyScenes = [`s${scene.index}`];
    state.gateReason = "";
  } else if (target.id === "lyric-offset") {
    state.lyricOffset = Math.min(1.5, Math.max(0.3, Number(target.value) || 0.9));
    if (state.lyricOn) queueLyrics();
  } else if (target.id === "lyric-words") {
    state.lyricDraft = target.value;
    if (state.lyricOn) queueLyrics();
  } else if (target.id === "brief") {
    state.brief = target.value;
    forgetApproval();
    queuePlan(360);
  } else if (target.id === "callback") {
    state.callback = target.value;
    queuePlan(360);
  } else if (target.dataset.scene === "action") {
    touchScene(Number(target.dataset.index), "action", target.value);
  } else if (target.dataset.slider) {
    state.sliders[target.dataset.slider] = Number(target.value);
    const val = target.parentElement.querySelector(".val");
    if (val) val.textContent = String(Math.round(Number(target.value) * 100));
    if (!state.locks.preset) state.preset = "";
    scheduleRecipe();
    scheduleSession();
  } else if (target.dataset.card) {
    const card = (state.cards || []).find((item) => item.at === target.dataset.card);
    if (card) card.text = target.value;
    scheduleRecipe();
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!state) return;
  if (target.dataset.act === "easy-cut-plan") {
    const file = target.files && target.files[0];
    if (!file) return;
    file.text().then((text) => {
      const plan = JSON.parse(text);
      if (!plan || !Array.isArray(plan.shots) || !plan.shots.length) throw new Error("no shots");
      state.easy.cutPlan = plan;
      state.easy.cloudPlan = null; // a new plan needs a new price and a new confirm click
      state.easy.cloudToken = "";
      state.easy.note = `Cut plan loaded: ${plan.shots.length} shots. Press Make to see its price.`;
    }).catch(() => { state.easy.note = "That file is not a cut plan (needs a shots list)."; }).finally(render);
  } else if (target.dataset.act === "easy-own-files") {
    uploadOwn(Array.from(target.files || []));
  } else if (target.dataset.act === "test-clip") {
    toggleTestClip(Number(target.dataset.index), target.checked);
  } else if (target.id === "lyric-align") {
    state.lyricOn = !!target.checked;
    state.lyricWords = [];
    state.lyricNote = "";
    render();
    if (state.lyricOn) queueLyrics();
  } else if (target.dataset.act === "scene-transition") {
    const index = Number(target.dataset.index);
    state.sceneTransitions = state.sceneTransitions || [];
    state.sceneTransitions[index] = target.value || "";
    render();
  } else if (target.dataset.act === "scene-look") {
    const scene = (state.scenes || [])[Number(target.dataset.index)];
    if (scene) {
      scene.dance_fx = target.value || "";
      scene.edited = true;
    }
    render();
  } else if (target.dataset.scene && target.dataset.scene !== "action") {
    const value = target.dataset.scene === "bars" ? Number(target.value) : target.value;
    touchScene(Number(target.dataset.index), target.dataset.scene, value);
    state.textOnly = false;
    state.onlyScenes = [];
    if (target.dataset.scene !== "bars") render();
  } else if (target.dataset.act === "block-form") {
    state.blocks[target.dataset.index].form = target.value;
    state.selected = Number(target.dataset.index);
    cancelStale();
    scheduleRecipe();
    render();
  } else if (target.dataset.act === "block-transition") {
    state.blocks[target.dataset.index].transition = target.value;
    state.selected = Number(target.dataset.index);
    cancelStale();
    scheduleRecipe();
  } else if (target.dataset.act === "block-hold") {
    state.blocks[target.dataset.index].hold = Number(target.value);
    state.selected = Number(target.dataset.index);
    cancelStale();
    scheduleRecipe();
    render();
  } else if (target.dataset.act === "live-ai") {
    state.liveAiRequested = !!target.checked;
  } else if (target.id === "continuous") {
    state.continuous = !!target.checked;
    forgetApproval();
    settleCut();
  } else if (target.id === "hero-file" && target.files && target.files[0]) {
    uploadHero(target.files[0]);
  } else if (target.dataset.act === "interpolate") {
    state.interpolate = !!target.checked;
  } else if ((target.id === "song-file" || target.id === "easy-file") && target.files[0]) {
    uploadSong(target.files[0]);
  } else if (target.id === "form-file" && target.files[0]) {
    uploadForm(target.files[0]);
  }
});

document.addEventListener("dragover", (event) => {
  const node = event.target;
  if (!node || !node.closest || !node.closest("[data-tour=song], [data-song-drop]")) return;
  event.preventDefault();
});

document.addEventListener("drop", (event) => {
  const node = event.target;
  const zone = node && node.closest ? node.closest("[data-tour=song], [data-song-drop]") : null;
  if (!zone || !state) return;
  event.preventDefault();
  const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) uploadSong(file);
});

// Your footage (Simple, Fine-tune): drop clips and images on the row.
document.addEventListener("dragover", (event) => {
  const zone = event.target && event.target.closest ? event.target.closest("[data-own-drop]") : null;
  if (!zone) return;
  event.preventDefault();
});

document.addEventListener("drop", (event) => {
  const zone = event.target && event.target.closest ? event.target.closest("[data-own-drop]") : null;
  if (!zone || !state || !state.easy) return;
  event.preventDefault();
  const files = Array.from((event.dataTransfer && event.dataTransfer.files) || []);
  if (files.length) uploadOwn(files);
});

document.getElementById("review-fix").addEventListener("click", () => {
  if (!state) return;
  runReview();
});

document.getElementById("generate").addEventListener("click", () => {
  if (!state) return;
  if (state.quality === "live") recordToggle();
  else generate();
});

document.getElementById("copy-diagnostics").addEventListener("click", () => {
  copyDiagnostics();
});

document.addEventListener("xeno-tour-step", (event) => {
  if (!state) return;
  if (document.body.dataset.advanced !== "1") {
    render();
    return;
  }
  const step = tourStepFor((event.detail && event.detail.target) || "");
  if (!step) return;
  const hash = railHash(step);
  const sameHash = (location.hash || "#simple") === hash;
  const sameStep = state.step === step;
  state.step = step;
  if (!sameHash) {
    location.hash = hash.slice(1);
    return;
  }
  if (!sameStep) render();
});

document.addEventListener("xeno-tour-end", () => {
  if (state && document.body.dataset.advanced !== "1") render();
});

function keyTarget(event) {
  return event.target && event.target.closest ? event.target : null;
}

function keyTyping(event) {
  const node = keyTarget(event);
  if (!node || !node.tagName) return false;
  if (node.tagName === "TEXTAREA" || node.tagName === "SELECT") return true;
  if (node.isContentEditable) return true;
  return node.tagName === "INPUT" && node.type !== "range";
}

const MCP_TOOLS = [
  ["list_registers", "List the story registers"],
  ["get_register", "Fetch one register"],
  ["set_register", "Switch the desk to a register"],
  ["list_presets", "List the named looks"],
  ["set_preset", "Apply a named look"],
  ["analyse_track", "Analyse a local audio file"],
  ["create_storyboard", "Turn a one-line brief into scene cards"],
  ["edit_scene_card", "Edit one scene card"],
  ["set_params", "Set the tier, palette, and faders"],
  ["apply_note", "Apply a director's note"],
  ["run_review", "Audit the storyboard"],
  ["render", "Render a tier"],
  ["get_render_status", "Read a render job"],
  ["get_frames", "Contact sheet for the current board"],
  ["list_versions", "List storyboard versions"],
  ["revert", "Restore a stored version"],
  ["export", "Export the recipe and the video"],
  ["storyboard", "Resource: the current storyboard"],
  ["lessons", "Resource: render lessons"],
  ["transitions", "Resource: transition catalogue"],
];

let paletteRows = [];

function paletteControls() {
  const rows = [];
  const seen = new Set();
  document.querySelectorAll("button[data-act], a[data-view], a.rail-link").forEach((node) => {
    if (node.closest("#command-palette")) return;
    const label = (node.innerText || node.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    if (!label || label.length > 90) return;
    const row = {
      kind: "control",
      label,
      blurb: "",
      act: node.dataset.act || "",
      step: node.dataset.step || "",
      quality: node.dataset.quality || "",
      method: node.dataset.method || "",
      view: node.dataset.view || "",
      id: node.id || "",
      href: node.getAttribute("href") || "",
    };
    const key = [row.act, row.step, row.quality, row.method, row.view, row.id, row.href, row.label].join("|");
    if (seen.has(key)) return;
    seen.add(key);
    rows.push(row);
  });
  MCP_TOOLS.forEach(([name, blurb]) => {
    rows.push({
      kind: "tool",
      label: name,
      blurb,
      act: "",
      step: "",
      quality: "",
      method: "",
      view: "",
      id: "",
      href: "",
    });
  });
  return rows;
}

function paintPalette() {
  const list = document.getElementById("palette-list");
  const input = document.getElementById("palette-q");
  if (!list) return;
  const query = (input && input.value ? input.value : "").trim().toLowerCase();
  const words = query ? query.split(/\s+/) : [];
  paletteRows = paletteControls().filter((row) => {
    const hay = `${row.label} ${row.blurb} ${row.act} ${row.kind}`.toLowerCase();
    return words.every((word) => hay.includes(word));
  }).slice(0, 12);
  if (!paletteRows.length) {
    list.innerHTML = `<li class="empty">Nothing matches.</li>`;
    return;
  }
  const at = Math.min(Number(state && state.paletteAt) || 0, paletteRows.length - 1);
  if (state) state.paletteAt = at;
  list.innerHTML = paletteRows
    .map((row, index) => {
      const kind = row.kind === "tool" ? "Tool" : "Control";
      const extra = row.blurb ? ` · ${esc(row.blurb)}` : "";
      return `<li><button type="button" class="${index === at ? "on" : ""}" data-act="palette-run" data-index="${index}"><b>${esc(row.label)}</b><span class="kind">${kind}${extra}</span></button></li>`;
    })
    .join("");
}

function openPalette() {
  const dialog = document.getElementById("command-palette");
  if (!dialog || !state) return;
  state.paletteAt = 0;
  const input = document.getElementById("palette-q");
  if (input) input.value = "";
  paintPalette();
  if (!dialog.open) dialog.showModal();
  if (input) input.focus();
}

function runPalette(row) {
  const dialog = document.getElementById("command-palette");
  if (dialog && dialog.open) dialog.close();
  if (!row || !state) return;
  if (row.kind === "tool") {
    goRail("connect");
    return;
  }
  if (row.act === "palette") return;
  if (row.act === "rail" && row.step) {
    goRail(row.step);
    return;
  }
  if (row.quality) {
    const button = document.querySelector(`[data-act="quality"][data-quality="${row.quality}"]`);
    if (button) button.click();
    return;
  }
  if (row.id) {
    const node = document.getElementById(row.id);
    if (node) node.click();
    return;
  }
  if (row.view) {
    const link = document.querySelector(`.views a[data-view="${row.view}"]`);
    if (link) link.click();
    return;
  }
  if (row.act) {
    const node = [...document.querySelectorAll(`[data-act="${row.act}"]`)].find((item) => {
      if (item.closest("#command-palette")) return false;
      if (row.step && item.dataset.step !== row.step) return false;
      if (row.method && item.dataset.method !== row.method) return false;
      return true;
    });
    if (node) node.click();
    return;
  }
  if (row.href) {
    const node = document.querySelector(`a[href="${row.href}"]`);
    if (node) node.click();
  }
}

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    const palette = document.getElementById("command-palette");
    if (palette && palette.open) palette.close();
    else openPalette();
    return;
  }
  const palette = document.getElementById("command-palette");
  if (palette && palette.open) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const count = paletteRows.length || 1;
      state.paletteAt = (Number(state.paletteAt || 0) + (event.key === "ArrowDown" ? 1 : -1) + count) % count;
      paintPalette();
    } else if (event.key === "Enter") {
      event.preventDefault();
      runPalette(paletteRows[Number(state.paletteAt || 0)]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      palette.close();
    }
    return;
  }
  if (document.querySelector("dialog[open]")) return;
  const tourCard = document.getElementById("tutorial-card");
  const tourOffer = document.getElementById("tutorial-offer");
  const touring = (tourCard && !tourCard.hidden) || (tourOffer && !tourOffer.hidden) || document.body.dataset.tour === "1";
  const current = keyTarget(event) && keyTarget(event).closest("[data-act=easy-vibe]");
  if (current && !touring && (event.key === "ArrowRight" || event.key === "ArrowDown" || event.key === "ArrowLeft" || event.key === "ArrowUp")) {
    const forward = event.key === "ArrowRight" || event.key === "ArrowDown";
    const cards = [...document.querySelectorAll("[data-act=easy-vibe]")];
    const index = cards.indexOf(current);
    if (index < 0) return;
    event.preventDefault();
    const nextCard = cards[(index + (forward ? 1 : -1) + cards.length) % cards.length];
    if (nextCard) nextCard.click();
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    if (document.body.dataset.advanced !== "1") {
      const make = document.querySelector("[data-act=easy-make]");
      if (make) {
        make.click();
        return;
      }
    }
    const generateButton = document.getElementById("generate");
    if (generateButton && document.body.dataset.advanced === "1") generateButton.click();
    return;
  }
  if (event.key === "Escape") {
    if (touring) return;
    if (state && state.recording) {
      event.preventDefault();
      recordToggle();
      return;
    }
    if (state && state.job && state.job.status === "running" && state.job.id) {
      event.preventDefault();
      ignoreJob = state.job.id;
      api(`/api/jobs/${state.job.id}/cancel`, { method: "POST" }).catch(() => {});
    }
    return;
  }
  if (keyTyping(event) || touring) return;
  if (event.key === " ") {
    const control = keyTarget(event) && keyTarget(event).closest("button, a, summary");
    if (control) return;
    const play = document.querySelector("[data-act=easy-play]");
    if (play) {
      event.preventDefault();
      play.click();
      return;
    }
    const player = document.getElementById("player");
    if (player) {
      event.preventDefault();
      if (player.paused) player.play().catch(() => {});
      else player.pause();
      return;
    }
    if (state && state.quality === "live") {
      event.preventDefault();
      playLive();
    }
    return;
  }
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const shots = [...document.querySelectorAll("[data-act=expand]")];
  if (!shots.length || !state) return;
  event.preventDefault();
  const at = shots.findIndex((button) => Number(button.dataset.index) === state.expanded);
  const delta = event.key === "ArrowRight" ? 1 : -1;
  const nextShot = shots[(Math.max(0, at) + delta + shots.length) % shots.length];
  if (nextShot) nextShot.click();
});

document.getElementById("advanced-toggle").addEventListener("click", () => {
  const on = document.body.dataset.advanced === "1";
  syncAdvanced(!on);
  if (state) render();
});

document.getElementById("open-about").addEventListener("click", () => {
  document.getElementById("about").showModal();
});

const paletteForm = document.querySelector("#command-palette form");
if (paletteForm) paletteForm.addEventListener("submit", (event) => event.preventDefault());

document.getElementById("open-settings").addEventListener("click", () => {
  if (!state) return;
  document.getElementById("endpoint").value = state.endpoint || "";
  document.getElementById(state.live ? "mode-live" : "mode-dry").checked = true;
  document.getElementById("addons").checked = !!state.addons;
  const paid = document.getElementById("paid-cloud");
  if (paid) {
    paid.checked = !!state.paidCloud;
    paid.disabled = state.paidCloudEnv === "on" || state.paidCloudEnv === "off";
    const why = document.getElementById("paid-cloud-env");
    if (why) why.textContent = state.paidCloudEnv ? `Set by XENO_PAID_CLOUD=${state.paidCloudEnv === "on" ? "1" : "0"} when the desk started.` : "";
  }
  const model = document.getElementById("video-model");
  if (model) model.value = state.videoModel === "ltx-25" ? "ltx-25" : "ltx-23";
  const folder = document.getElementById("library-folder");
  if (folder) folder.value = state.libraryFolder || "";
  const faces = document.getElementById("exclude-faces");
  if (faces) faces.checked = state.excludeFaces !== false;
  const pdUs = document.getElementById("allow-pd-us");
  if (pdUs) pdUs.checked = !!state.allowPdUs;
  document.getElementById("settings").showModal();
});

document.getElementById("save-settings").addEventListener("click", () => {
  if (!state) return;
  state.live = document.getElementById("mode-live").checked;
  state.endpoint = document.getElementById("endpoint").value.trim() || "http://127.0.0.1:8188";
  state.addons = document.getElementById("addons").checked;
  writeAddons(state.addons);
  const paid = document.getElementById("paid-cloud");
  if (paid && !paid.disabled) {
    state.paidCloud = paid.checked;
    writePaidCloud(state.paidCloud);
  }
  if (!state.paidCloud && state.easy) {
    state.easy.cloud = false;
    state.easy.cloudToken = "";
    state.easy.cloudPlan = null;
  }
  const model = document.getElementById("video-model");
  state.videoModel = model && model.value === "ltx-25" ? "ltx-25" : "ltx-23";
  writeVideoModel(state.videoModel);
  const folder = document.getElementById("library-folder");
  state.libraryFolder = folder ? folder.value.trim() : state.libraryFolder || "";
  const faces = document.getElementById("exclude-faces");
  state.excludeFaces = faces ? faces.checked : state.excludeFaces !== false;
  const pdUs = document.getElementById("allow-pd-us");
  state.allowPdUs = pdUs ? pdUs.checked : !!state.allowPdUs;
  writeLibraryPrefs();
  state.libraryItems = null;
  state.libraryPick = null;
  document.getElementById("settings").close();
  render();
  refreshComfy();
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!target || !target.dataset || target.dataset.act !== "pick-model") return;
  pickModel(target.dataset.id, target.value);
});

async function pickModel(id, file) {
  if (!id || !file) return;
  try {
    const response = await api("/api/setup/pick", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, file }),
    });
    if (!response.ok) return;
  } catch (error) {
    return;
  }
  await loadSetup();
  if (state && state.view === "setup") render();
}

document.addEventListener("change", (event) => {
  const field = event.target && event.target.id === "easy-endpoint" ? event.target : null;
  if (!field || !state) return;
  state.endpoint = field.value.trim() || "http://127.0.0.1:8188";
  const settings = document.getElementById("endpoint");
  if (settings) settings.value = state.endpoint;
  refreshComfy().then(() => render());
});

async function refreshComfy() {
  const endpoint = (state && state.endpoint) || "http://127.0.0.1:8188";
  let data = null;
  try {
    const response = await api(`/api/comfy?url=${encodeURIComponent(endpoint)}`);
    if (response.ok) data = await response.json();
  } catch (error) {
    data = null;
  }
  const ok = !!(data && data.ok);
  const label = ok ? "ComfyUI connected" : "ComfyUI not connected";
  const node = document.getElementById("comfy-status");
  if (node) {
    node.dataset.ok = ok ? "1" : "0";
    node.textContent = label;
  }
  const note = document.getElementById("comfy-settings-status");
  if (note) note.textContent = `${label}. The desk pings /system_stats on ${endpoint}.`;
  if (state) state.comfyOk = ok;
}

const viewNav = document.querySelector(".views");
if (viewNav) {
  viewNav.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-view]");
    if (!link || !state || document.body.dataset.advanced !== "1") return;
    const view = link.dataset.view;
    const step = view === "notes" ? "notes" : view === "connect" ? "connect" : view === "setup" ? "setup" : view === "director" ? "shots" : "song";
    state.step = step;
    if ((location.hash || "#simple") === railHash(step)) {
      event.preventDefault();
      render();
    }
  });
}

window.addEventListener("hashchange", () => {
  if (!state) return;
  if (viewFromHash() === "notes" && !state.pending) {
    if (!state.note) state.note = SAMPLE_NOTE;
    state.notesOpen = true;
    settleNotes();
    return;
  }
  render();
});

document.addEventListener("dragstart", (event) => {
  if (event.target.id !== "climax-token") return;
  event.dataTransfer.setData("text/plain", "climax");
  event.dataTransfer.effectAllowed = "move";
});

document.addEventListener("dragover", (event) => {
  const card = event.target.closest && event.target.closest(".scene");
  if (!card) return;
  event.preventDefault();
  card.classList.add("drop");
});

document.addEventListener("dragleave", (event) => {
  const card = event.target.closest && event.target.closest(".scene");
  if (card) card.classList.remove("drop");
});

document.addEventListener("drop", (event) => {
  const card = event.target.closest && event.target.closest(".scene");
  if (!card || !state) return;
  event.preventDefault();
  card.classList.remove("drop");
  const index = Number(card.dataset.index);
  state.climax = index;
  planStory({ climax: index });
});

async function interpretNote(shouldRender) {
  const note = (state.note || "").trim();
  if (!note) {
    state.noteStatus = "Write what you saw.";
    state.pending = null;
    if (shouldRender) render();
    return;
  }
  if (state.noteBusy) return;
  state.noteBusy = true;
  state.noteStatus = "Reading the note…";
  if (shouldRender) render();
  try {
    const response = await api("/api/notes/interpret", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_id: state.audioId,
        note,
        scenes: state.scenes,
        quality: state.quality,
        brief: state.brief,
        addons: !!state.addons,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      state.pending = null;
      state.noteStatus = data.detail || "The note did not parse.";
    } else {
      state.pending = data;
      state.lessonOffer = data.lesson_offer || null;
      state.notesOpen = true;
      const first = (data.diff || [])[0];
      state.noteStatus = first ? `${first.label} · ${first.field}: ${first.old} → ${first.new}` : data.rationale || "Patch ready.";
    }
  } catch (error) {
    state.pending = null;
    state.noteStatus = "The note interpreter did not answer.";
  } finally {
    state.noteBusy = false;
    render();
  }
}

async function confirmNote() {
  if (!state.pending || !state.pending.patch || state.noteBusy) return;
  cancelStale();
  state.noteBusy = true;
  state.noteStatus = "Rendering the changed segments…";
  render();
  try {
    const response = await api("/api/notes/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_id: state.audioId,
        note: state.note,
        patch: state.pending.patch,
        scenes: state.scenes,
        quality: state.quality,
        video: state.video,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      state.noteStatus = data.detail || "The patch did not apply.";
    } else {
      state.scenes = data.scenes;
      state.blocks = data.blocks;
      state.versions = data.versions || [];
      state.versionId = data.current;
      state.pending = null;
      state.lessonOffer = data.lesson_offer || state.lessonOffer;
      state.noteStatus = data.detail || "Cut updated.";
      if (data.video) state.videoLabel = data.version && data.version.label ? data.version.label : state.videoLabel;
      scheduleRecipe();
    }
  } catch (error) {
    state.noteStatus = "The rerender did not finish.";
  } finally {
    state.noteBusy = false;
    render();
  }
}

function watchVersion(id) {
  const version = (state.versions || []).find((item) => item.id === id);
  if (!version) return;
  state.versionId = version.id;
  state.flipId = version.id;
  if (version.video) {
    state.video = version.video;
    state.videoLabel = version.label || "Noted cut";
  }
  state.noteStatus = `Showing ${version.label || version.note}.`;
  render();
}

async function revertVersion(id) {
  const response = await api("/api/notes/revert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio_id: state.audioId, version_id: id }),
  });
  const data = await response.json();
  if (!response.ok) {
    state.noteStatus = data.detail || "That version is gone.";
    render();
    return;
  }
  state.scenes = data.scenes;
  state.blocks = data.blocks;
  state.versions = data.versions || [];
  state.versionId = data.current;
  state.pending = null;
  if (data.video) {
    state.video = data.video;
    state.videoLabel = data.version && data.version.label ? data.version.label : "Reverted";
  }
  state.noteStatus = `Reverted. ${state.videoLabel}.`;
  scheduleRecipe();
  render();
}

function flipVersions() {
  const list = state.versions || [];
  if (list.length < 2) {
    state.noteStatus = "Confirm a note, then flip between that cut and the draft.";
    render();
    return;
  }
  const current = state.flipId || state.versionId;
  const index = Math.max(0, list.findIndex((item) => item.id === current));
  const next = list[(index + 1) % list.length];
  watchVersion(next.id);
}

async function saveLesson() {
  const offer = state.lessonOffer || (state.pending && state.pending.lesson_offer);
  if (!offer) return;
  const response = await api("/api/lessons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(offer),
  });
  const data = await response.json();
  if (!response.ok) {
    state.noteStatus = data.detail || "The lesson did not save.";
    render();
    return;
  }
  state.savedLessons = (state.savedLessons || []).concat([data.lesson]);
  state.lessonOffer = null;
  if (state.pending) state.pending.lesson_offer = null;
  state.noteStatus = "Saved as a lesson. The critic will raise it next time.";
  render();
}

async function settleNotes() {
  try {
    const lessons = await api("/api/lessons");
    if (lessons.ok) {
      const data = await lessons.json();
      state.savedLessons = data.saved || [];
      state.builtinLessons = data.builtin || [];
    }
  } catch (error) {
    state.savedLessons = state.savedLessons || [];
  }
  try {
    const critic = await api("/api/notes/critic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio_id: state.audioId, scenes: state.scenes, sample: state.view === "notes" }),
    });
    if (critic.ok) {
      const data = await critic.json();
      state.suggestions = data.notes || [];
    }
  } catch (error) {
    state.suggestions = state.suggestions || [];
  }
  try {
    const ledger = await api("/api/v1/ledger");
    if (ledger.ok) {
      const data = await ledger.json();
      state.ledger = data.rounds || [];
      state.ledgerMarkdown = data.markdown || "";
    }
  } catch (error) {
    state.ledger = state.ledger || [];
  }
  try {
    const versions = await api(`/api/notes/versions?audio_id=${encodeURIComponent(state.audioId)}`);
    if (versions.ok) {
      const data = await versions.json();
      if ((data.versions || []).length) {
        state.versions = data.versions;
        state.versionId = data.current;
      }
    }
  } catch (error) {
    /* the list fills after the first confirm */
  }
  if ((state.view === "notes" || state.notesOpen) && state.note) {
    await interpretNote(false);
    return;
  }
  const active = document.activeElement;
  if (active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) return;
  render();
}

function setupBanner() {
  const setup = state && state.setup;
  if (!setup || !(setup.missing_required || []).length || state.setupHidden) return "";
  const names = setup.missing_required.join(", ");
  return `<p class="setup-banner">Live restyle still needs ${esc(names)}. <a href="#setup">Open Setup</a>. Try the demo runs without it.</p>`;
}

function renderSetup() {
  const setup = state.setup;
  if (!setup) {
    return `<section class="panel"><p class="boot">Checking this machine…</p></section>`;
  }
  const tier = setup.tier || {};
  const cards = (setup.models || [])
    .map((model) => {
      const job = (state.downloads || {})[model.id] || {};
      const running = job.status === "running";
      const width = Math.round((job.progress || 0) * 100);
      const status = model.present
        ? "Installed"
        : model.manual
          ? "Place the local file"
          : job.status === "error"
            ? job.detail || job.error
            : job.detail || (model.required ? "Needed for a live restyle" : "Optional");
      const button = model.present || model.manual
        ? ""
        : `<button type="button" class="generate${running ? " is-loading" : ""}" data-act="download-model" data-id="${esc(model.id)}" ${running ? "disabled" : ""}>${running ? "Downloading" : "Download"} · ${esc(model.size_label)}</button>`;
      const variants = model.variants || [];
      const picker = variants.length
        ? `<label>File<select data-act="pick-model" data-id="${esc(model.id)}" aria-label="Weight file for ${esc(model.name)}">${variants
            .map((file) => `<option value="${esc(file)}"${file === model.chosen ? " selected" : ""}>${esc(file.split("/").pop())}</option>`)
            .join("")}</select></label>`
        : "";
      return `<article class="model-card">
        <header><strong>${esc(model.name)}</strong><span>${esc(model.badge || (model.required ? "Fast fallback" : "Optional"))}</span></header>
        <p>${esc(model.detail)}</p>
        <p class="status">${esc(status)}${model.filename ? ` · ${esc(model.filename)}` : ""}</p>
        ${picker}
        ${running ? `<div class="track"><span style="width:${width}%"></span></div>` : ""}
        ${button}
      </article>`;
    })
    .join("");
  const llm = setup.llm || {};
  const llmJob = (state.downloads || {}).llm || {};
  return `<div class="setup">
    <section class="panel">
      <p class="kicker">Setup check</p>
      <h2>${esc(tier.label || "This machine")}</h2>
      <p>${esc(tier.detail || "")}</p>
      <p class="note">${esc(setup.disk ? setup.disk.free_label : "")} on the models drive. ${esc(setup.try_it || "")}</p>
      <p class="note">${esc((setup.stems || {}).detail || "")}</p>
    </section>
    <section class="panel models">${cards}</section>
    <section class="panel">
      <p class="kicker">Optional</p>
      <h2>Local notes model</h2>
      <p>${esc(llm.detail || "")}</p>
      ${
        llm.present
          ? `<p class="status">Ollama is up.</p>`
          : `<button type="button" class="ghost${llmJob.status === "running" ? " is-loading" : ""}" data-act="download-model" data-id="llm"${llmJob.status === "running" ? " disabled" : ""}>${llmJob.status === "running" ? "Asking Ollama…" : "Use Ollama if it is installed"}</button>`
      }
      <p class="note">Ableton is not part of this desk.</p>
    </section>
    <section class="panel">
      <p class="kicker">Optional</p>
      <h2>Faster picture</h2>
      ${(setup.extras || [])
        .map(
          (extra) => `<article class="model-card">
            <header><strong>${esc(extra.name)}</strong><span>${extra.present ? "Installed" : "Not installed"}</span></header>
            <p>${esc(extra.detail)}</p>
          </article>`,
        )
        .join("")}
      <p class="note">Frame fill uses ${esc(setup.interpolate || "minterpolate")}. Turn it on beside Turbo, Draft, or Final. Live+AI and TensorRT stay off the base install.</p>
      <button type="button" class="ghost" data-act="check-extra">Check again</button>
    </section>
  </div>`;
}

async function loadSetup() {
  try {
    const response = await api("/api/setup");
    if (!response.ok) return;
    state.setup = await response.json();
    const extra = (state.setup.extras || []).find((item) => item.id === "live-ai");
    state.liveAiPresent = !!(extra && extra.present);
  } catch (error) {
    state.setup = state.setup || null;
  }
}

async function playLive() {
  if (!window.XENO_LIVE) return;
  try {
    await window.XENO_LIVE.play();
  } catch (error) {
    const note = document.getElementById("live-note");
    if (note) note.textContent = "Press Play to start the song with the picture.";
  }
}

async function recordToggle() {
  if (!window.XENO_LIVE) return;
  const note = document.getElementById("live-note");
  if (window.XENO_LIVE.recording()) {
    let blob = null;
    try {
      blob = await window.XENO_LIVE.stopRecord();
    } catch (error) {
      blob = null;
    }
    state.recording = false;
    paintGenerate();
    const button = document.querySelector("[data-act='live-record']");
    if (button) button.textContent = "Record";
    if (!blob || !blob.size) {
      if (note) note.textContent = "The recording was empty.";
      return;
    }
    const body = new FormData();
    body.append("file", blob, "live.webm");
    const response = await api("/api/live/record", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) {
      if (note) note.textContent = data.detail || "The recording did not save.";
      return;
    }
    state.guideId = data.id;
    state.video = data.url;
    state.videoLabel = "Live recording";
    if (note) {
      note.dataset.lock = "1";
      note.textContent = data.detail || "Recorded.";
    }
    return;
  }
  try {
    await window.XENO_LIVE.play();
    await window.XENO_LIVE.startRecord();
  } catch (error) {
    if (note) note.textContent = "This browser did not start the recording.";
    return;
  }
  state.recording = true;
  paintGenerate();
  const button = document.querySelector("[data-act='live-record']");
  if (button) button.textContent = "Stop";
}

async function conformStory() {
  const source = state.heldBoard && state.heldBoard.length ? state.heldBoard : state.board;
  if (!source || !source.length) return;
  const response = await api("/api/conform", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio_id: state.audioId || "demo", scenes: source }),
  });
  const data = await response.json();
  if (!response.ok) return;
  state.board = data.scenes;
  state.storyApproved = false;
  await settleCut({ full: true });
}

// Your own clips and images for the Simple cut: the dropped or picked files go to work/ui/own/<id>/ (POST /api/own);
// the Make body sends own_id and the server scans that folder (images lead the morphs, clips are cut in on the beat).
async function uploadOwn(files) {
  if (!files.length || !state.easy) return;
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  state.easy.ownNote = `Attaching ${files.length} file${files.length === 1 ? "" : "s"}...`;
  render();
  const response = await api("/api/own", { method: "POST", body });
  const data = await response.json();
  if (!response.ok) {
    state.easy.ownNote = data.detail || "Those files did not attach.";
    render();
    return;
  }
  state.easy.ownId = data.id;
  state.easy.ownFolder = "";
  state.easy.ownNote = data.detail || `${data.images} images, ${data.clips} clips.`;
  render();
}

async function uploadHero(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await api("/api/hero", { method: "POST", body });
  const data = await response.json();
  if (!response.ok) {
    window.alert(data.detail || "That picture did not attach.");
    return;
  }
  state.heroId = data.id;
  state.heroUrl = data.url;
  state.storyApproved = false;
  await settleCut({ full: true });
}

async function tryDemo() {
  state.live = false;
  if (state.audioId !== "demo") {
    const response = await api("/api/demo");
    if (response.ok) adoptSession(await response.json());
  }
  if (!state.locks || !state.locks.register) state.register = "pynchon";
  state.quality = "live";
  await settleCut({ full: true });
  playLive();
}

async function downloadModel(id) {
  state.downloads = state.downloads || {};
  const response = await api("/api/setup/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  const data = await response.json();
  if (!response.ok) {
    state.downloads[id] = { status: "error", detail: data.detail || "The download did not start.", error: data.detail };
    render();
    return;
  }
  state.downloads[id] = data;
  render();
  pollDownload(id);
}

async function pollDownload(id) {
  const response = await api(`/api/setup/download/${encodeURIComponent(id)}`);
  if (!response.ok) return;
  const data = await response.json();
  state.downloads = state.downloads || {};
  state.downloads[id] = data;
  if (state.view === "setup") render();
  if (data.status === "running") {
    setTimeout(() => pollDownload(id), 500);
    return;
  }
  await loadSetup();
  if (state.view === "setup") render();
}

async function copyText(text) {
  const value = text || "Xenoform has no extra diagnostics yet.";
  try {
    await navigator.clipboard.writeText(value);
    if (state) state.noteStatus = "Diagnostics copied.";
  } catch (error) {
    window.prompt("Copy diagnostics", value);
  }
}

async function copyDiagnostics() {
  const response = await api("/api/diagnostics");
  const data = response.ok ? await response.json() : {};
  const job = state && state.job && state.job.diagnostics;
  await copyText([data.diagnostics, job].filter(Boolean).join("\n\n"));
}

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!target || target.id !== "library-tag" || !state) return;
  state.libraryTag = target.value || "";
  paintLibraryGrid();
});

function libraryQuery() {
  const join = morphJoin();
  const scene = join.scene || {};
  const start = Number(scene.start || 0);
  const section = (state.sections || []).find((row) => Number(row.start) <= start && start < Number(row.end)) || {};
  return {
    folder: state.libraryFolder || "",
    library_folder: state.libraryFolder || "",
    exclude_faces: state.excludeFaces !== false,
    allow_pd_us: !!state.allowPdUs,
    vibe: (state.easy && state.easy.vibe) || "",
    mood: scene.mood || "",
    energy: section.level != null ? Number(section.level) : Number(state.energy || 0),
    beat: scene.beat || "",
    section: section.label || "",
    pinned: state.libraryPins || [],
    banned: state.libraryBans || [],
  };
}

function libraryFallback(item) {
  const letter = esc(String(item.category || item.id || "?").trim().charAt(0).toUpperCase() || "?");
  return `<div class="library-fallback" aria-hidden="true">${letter}</div>`;
}

function libraryMatches(item, query) {
  if (!query) return true;
  const hay = [item.id, item.category, item.motion, item.silhouette, item.licence_bucket]
    .concat(item.tags || [], item.moods || [])
    .join(" ")
    .toLowerCase();
  return query.split(/\s+/).every((word) => word && hay.indexOf(word) >= 0);
}

function paintLibraryGrid() {
  const grid = document.getElementById("library-grid");
  if (!grid || !state) return;
  const query = String(state.libraryTag || "").trim().toLowerCase();
  const items = (state.libraryItems || []).filter((item) => libraryMatches(item, query));
  if (!state.libraryItems) {
    grid.innerHTML = "";
    return;
  }
  if (!items.length) {
    grid.innerHTML = `<p class="note">${state.libraryItems.length ? "No item has that tag." : "This folder has no items yet."}</p>`;
    return;
  }
  const pins = state.libraryPins || [];
  const bans = state.libraryBans || [];
  grid.innerHTML = items
    .slice(0, 48)
    .map((item) => {
      const pinned = pins.indexOf(item.id) >= 0;
      const banned = bans.indexOf(item.id) >= 0;
      const thumb = item.thumb
        ? `<img class="library-thumb" alt="" src="${esc(media(item.thumb))}" />`
        : libraryFallback(item);
      const tags = (item.tags || []).slice(0, 3).join(" · ");
      return `<article class="library-card${pinned ? " is-pinned" : ""}${banned ? " is-banned" : ""}">
        ${thumb}
        <h4>${esc(item.id)}</h4>
        <p>${esc(item.category || "")}${tags ? " · " + esc(tags) : ""}</p>
        <div class="library-actions">
          <button type="button" class="ghost" data-act="library-pin" data-id="${esc(item.id)}" aria-pressed="${pinned ? "true" : "false"}">${pinned ? "Pinned" : "Pin"}</button>
          <button type="button" class="ghost" data-act="library-ban" data-id="${esc(item.id)}" aria-pressed="${banned ? "true" : "false"}">${banned ? "Banned" : "Ban"}</button>
        </div>
      </article>`;
    })
    .join("");
  grid.querySelectorAll("img.library-thumb").forEach((img) => {
    img.addEventListener("error", () => {
      const letter = (img.alt || "?").slice(0, 1) || "?";
      const fallback = document.createElement("div");
      fallback.className = "library-fallback";
      fallback.textContent = letter;
      img.replaceWith(fallback);
    });
  });
}

function paintLibrary() {
  const note = document.getElementById("library-note");
  const pair = document.getElementById("library-pair");
  if (!note || !state) return;
  const pick = state.libraryPick;
  if (state.libraryNote) note.textContent = state.libraryNote;
  else if (!state.libraryItems) note.textContent = "Reading the library…";
  else if (!state.libraryItems.length) note.textContent = "No library.json in this folder. Run python scripts/fetch_sample_library.py for a few procedural shapes.";
  else {
    const hidden = [];
    if (state.excludeFaces !== false) hidden.push("faces hidden");
    if (!state.allowPdUs) hidden.push("PD-US only hidden");
    note.textContent = `${state.libraryItems.length} items. ${hidden.join(". ")}.`;
  }
  if (pair) {
    if (pick && pick.source) {
      const target = pick.target ? pick.target.id : "—";
      const chain = pick.chain ? "Morph chain" : "Tag match";
      const credit = (pick.credits || [])[0] ? ` ${pick.credits[0]}` : "";
      pair.textContent = `${pick.source.id} → ${target}. ${chain}.${credit}`;
    } else pair.textContent = pick && pick.reason ? pick.reason : "";
  }
  paintLibraryGrid();
}

function scoreLane() {
  const rows = state.score || [];
  const duration = Number(state.duration || 1) || 1;
  if (!rows.length) {
    return `<div class="tl-score" id="score-lane"><span class="tl-qa">Reading the score…</span></div>`;
  }
  const bits = rows
    .map((row) => {
      const width = Math.max(8, ((Number(row.end) - Number(row.start)) / duration) * 100);
      const object = row.source ? `${row.source} → ${row.target || "—"}` : row.becomes;
      return `<button type="button" class="score-cue role-${esc(row.role)}" data-act="score-rerender" data-start="${Number(row.start)}" data-end="${Number(row.end)}" style="width:${width}%"><b>${esc(row.label)} · ${esc(row.role)}</b><small>${esc(object)}</small></button>`;
    })
    .join("");
  return `<div class="tl-score" id="score-lane">${bits}</div>`;
}

function paintScore() {
  const lane = document.getElementById("score-lane");
  if (!lane || !state) return;
  const fresh = document.createElement("div");
  fresh.innerHTML = scoreLane();
  const next = fresh.firstElementChild;
  if (next) lane.replaceWith(next);
}

function scheduleOpener() {
  const card = document.getElementById("drop-open");
  if (!card || !state) return;
  const key = state.audioId || "demo";
  if (state.opener && state.opener.audioId === key && state.opener.ready) return;
  const token = (scheduleOpener.token = (scheduleOpener.token || 0) + 1);
  api("/api/opener", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      audio_id: key,
      vibe: (state.easy && state.easy.vibe) || "",
      library_folder: state.libraryFolder || "",
      exclude_faces: state.excludeFaces !== false,
      allow_pd_us: !!state.allowPdUs,
      library_pins: state.libraryPins || [],
      library_bans: state.libraryBans || [],
    }),
  })
    .then(async (response) => {
      if (token !== scheduleOpener.token || !state) return;
      const body = response.ok ? await response.json() : { ready: false, line: "The drop did not read." };
      body.audioId = key;
      state.opener = body;
      paintOpener();
    })
    .catch(() => {});
}

function paintOpener() {
  const card = document.getElementById("drop-open");
  const opener = state && state.opener;
  if (!card || !opener) return;
  const title = card.querySelector("h3");
  const line = card.querySelector(".drop-line");
  const button = card.querySelector("[data-act='open-drop']");
  const pair = opener.source && opener.target ? `${opener.source} → ${opener.target}` : (opener.becomes || "Impact");
  if (title) title.textContent = opener.ready ? pair : "Finding the downbeat…";
  if (line) line.textContent = opener.line || "";
  if (button) button.disabled = !opener.ready;
}

function openDrop() {
  const opener = state && state.opener;
  if (!opener || !opener.ready) return;
  let audio = document.getElementById("drop-audio");
  if (!audio) {
    audio = document.createElement("audio");
    audio.id = "drop-audio";
    audio.preload = "auto";
    document.body.appendChild(audio);
  }
  const src = media(state.audioUrl || "/media/audio/demo");
  if (audio.getAttribute("src") !== src) audio.src = src;
  const at = Number(opener.at) || 0;
  const start = () => {
    try {
      audio.currentTime = at;
    } catch (err) {
      /* the element may not be seekable yet */
    }
    audio.play().catch(() => {});
  };
  if (audio.readyState >= 1) start();
  else audio.addEventListener("loadedmetadata", start, { once: true });
  const card = document.getElementById("drop-open");
  if (!card) return;
  card.classList.add("is-hit");
  window.setTimeout(() => card.classList.remove("is-hit"), 80);
}

function scheduleScore() {
  if (!document.getElementById("score-lane") || !state) return;
  const token = (scheduleScore.token = (scheduleScore.token || 0) + 1);
  api("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      audio_id: state.audioId || "",
      vibe: (state.easy && state.easy.vibe) || "",
      library_folder: state.libraryFolder || "",
      exclude_faces: state.excludeFaces !== false,
      allow_pd_us: !!state.allowPdUs,
      library_pins: state.libraryPins || [],
      library_bans: state.libraryBans || [],
    }),
  })
    .then(async (response) => {
      if (token !== scheduleScore.token || !state) return;
      state.score = response.ok ? (await response.json()).segments || [] : [];
      paintScore();
    })
    .catch(() => {
      if (token !== scheduleScore.token || !state) return;
      state.score = [];
      paintScore();
    });
}

function rerenderSection(start, end) {
  const scenes = (state.scenes || []).filter((scene) => {
    const a = Number(scene.start) || 0;
    const b = Number(scene.end) || a;
    return b > start && a < end;
  });
  const ids = scenes.map((scene) => `s${scene.index}`);
  if (!ids.length) return;
  state.textOnly = true;
  state.onlyScenes = ids;
  generate();
}

function readMorphHit() {
  try {
    return localStorage.getItem("xeno-morph-hit") !== "0";
  } catch (err) {
    return true;
  }
}

function writeMorphHit(on) {
  try {
    localStorage.setItem("xeno-morph-hit", on ? "1" : "0");
  } catch (err) {}
}

function readVideoModel() {
  try {
    return localStorage.getItem("xeno-video-model") === "ltx-25" ? "ltx-25" : "ltx-23";
  } catch (err) {
    return "ltx-23";
  }
}

function writeVideoModel(value) {
  try {
    localStorage.setItem("xeno-video-model", value === "ltx-25" ? "ltx-25" : "ltx-23");
  } catch (err) {}
}

function scheduleLibrary() {
  if (!document.getElementById("library-browser") || !state) return;
  const token = (scheduleLibrary.token = (scheduleLibrary.token || 0) + 1);
  const query = libraryQuery();
  const params = new URLSearchParams({
    folder: query.folder,
    exclude_faces: query.exclude_faces ? "true" : "false",
    allow_pd_us: query.allow_pd_us ? "true" : "false",
  });
  paintLibrary();
  Promise.all([
    api("/api/library?" + params.toString()),
    api("/api/library/pick", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(query),
    }),
  ])
    .then(async ([listResponse, pickResponse]) => {
      if (token !== scheduleLibrary.token || !state) return;
      if (!listResponse.ok) {
        state.libraryNote = "The library did not answer.";
        state.libraryItems = [];
      } else {
        const data = await listResponse.json();
        state.libraryItems = data.items || [];
        state.libraryNote = data.missing_index
          ? "No library.json in this folder. Run python scripts/fetch_sample_library.py for a few procedural shapes."
          : "";
      }
      if (pickResponse.ok) state.libraryPick = await pickResponse.json();
      paintLibrary();
    })
    .catch(() => {
      if (token !== scheduleLibrary.token || !state) return;
      state.libraryNote = "The library did not answer.";
      state.libraryItems = [];
      paintLibrary();
    });
}

function readPaidCloud() {
  try {
    return localStorage.getItem("xeno-paid-cloud") === "1";
  } catch (err) {
    return false;
  }
}

function writePaidCloud(on) {
  try {
    localStorage.setItem("xeno-paid-cloud", on ? "1" : "0");
  } catch (err) {}
}

// Paid cloud renders: off unless XENO_PAID_CLOUD=1, comfy.paid_cloud, or the Settings opt-in.
function paidCloudFor(data, previous) {
  const info = (data && data.paid_cloud) || null;
  const env = info ? String(info.env || "") : previous ? previous.paidCloudEnv || "" : "";
  if (env === "on") return true;
  if (env === "off") return false;
  if (previous && previous.paidCloud != null) return !!previous.paidCloud;
  return readPaidCloud() || !!(info && info.config);
}

function readAddons() {
  try {
    return localStorage.getItem("xeno-addons") === "1";
  } catch (err) {
    return false;
  }
}

function writeAddons(on) {
  try {
    localStorage.setItem("xeno-addons", on ? "1" : "0");
  } catch (err) {}
}

function readLibraryFolder() {
  try {
    return localStorage.getItem("xeno-library-folder") || "";
  } catch (err) {
    return "";
  }
}

function readExcludeFaces() {
  try {
    const value = localStorage.getItem("xeno-exclude-faces");
    if (value == null) return true;
    return value !== "0";
  } catch (err) {
    return true;
  }
}

function readAllowPdUs() {
  try {
    return localStorage.getItem("xeno-allow-pd-us") === "1";
  } catch (err) {
    return false;
  }
}

function readIdList(key) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
  } catch (err) {
    return [];
  }
}

function writeLibraryPrefs() {
  try {
    localStorage.setItem("xeno-library-folder", state.libraryFolder || "");
    localStorage.setItem("xeno-exclude-faces", state.excludeFaces === false ? "0" : "1");
    localStorage.setItem("xeno-allow-pd-us", state.allowPdUs ? "1" : "0");
    localStorage.setItem("xeno-library-pins", JSON.stringify(state.libraryPins || []));
    localStorage.setItem("xeno-library-bans", JSON.stringify(state.libraryBans || []));
  } catch (err) {}
}

function syncAdvanced(next) {
  let on = false;
  try {
    if (next === undefined) on = localStorage.getItem("xeno-advanced") === "1";
    else {
      on = Boolean(next);
      localStorage.setItem("xeno-advanced", on ? "1" : "0");
    }
  } catch (error) {
    on = Boolean(next);
  }
  document.body.dataset.advanced = on ? "1" : "0";
  const button = document.getElementById("advanced-toggle");
  if (button) {
    button.setAttribute("aria-pressed", on ? "true" : "false");
    button.textContent = on ? "Advanced on" : "Advanced";
  }
}

async function boot() {
  syncAdvanced();
  try {
    const response = await api("/api/demo");
    if (!response.ok) throw new Error("demo unavailable");
    adoptSession(await response.json());
    setInterval(pollAgent, 3000);
    await loadSetup();
    if (viewFromHash() === "notes") {
      state.note = SAMPLE_NOTE;
      state.notesOpen = true;
    }
    await settleCut({ full: true });
    await settleNotes();
    refreshComfy();
    setInterval(refreshComfy, 8000);
    Promise.all([loadVideos(), loadVibes(), loadTransitions(), loadSimpleOptions()]).then(() => render());
    if (window.XENO_TUTORIAL) window.XENO_TUTORIAL.ready();
  } catch (error) {
    document.getElementById("app").innerHTML = `<div class="error-panel"><h2>The desk could not open the demo.</h2><p>${esc(error.message)}. The reference cut is examples/demo_base.mp4.</p></div>`;
    document.body.dataset.ready = "1";
  }
}

boot();

// Forms slider / number box: live value without re-rendering on every tick, re-render on change.
document.addEventListener("input", (ev) => {
  const el = ev.target;
  if (!el || !el.dataset || el.dataset.act !== "easy-morphs" || !state.easy) return;
  const n = Math.max(1, Math.min(120, Math.round(Number(el.value) || 1)));
  state.easy.morphs = n;
  const box = el.closest(".morph-count");
  if (box) box.querySelectorAll("input").forEach((i) => { if (i !== el) i.value = String(Math.min(Number(i.max), n)); });
  const hint = box && box.querySelector(".guard-live");
  if (hint) hint.textContent = morphGuardText(n);
});
document.addEventListener("change", (ev) => {
  const el = ev.target;
  if (el && el.dataset && el.dataset.act === "easy-morphs") render();
});

// Fine-tune and More vibes remember whether they were open.
document.addEventListener("toggle", (ev) => {
  const el = ev.target;
  if (!el || !el.id) return;
  const key = { "fine-tune": "xeno-finetune", "more-vibes": "xeno-more-vibes" }[el.id];
  if (!key) return;
  try {
    localStorage.setItem(key, el.open ? "1" : "0");
  } catch (err) {}
}, true);

// Guardrails Expert override toggle (persisted).
(function guardExpert() {
  const box = document.getElementById("guard-expert");
  if (!box) return;
  box.checked = localStorage.getItem("xeno-guard-expert") === "1";
  box.addEventListener("change", () => localStorage.setItem("xeno-guard-expert", box.checked ? "1" : "0"));
})();
