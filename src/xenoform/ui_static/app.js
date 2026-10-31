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

// One desk. The tool pages keep their own hash (#setup, #connect); every other hash is the desk, and the old Director
// desk's hashes (#director, #scene, #notes, #simple/desk, ...) land on it and are tidied to #simple by easyPhaseFromHash.
function viewFromHash() {
  const name = (location.hash || "#simple").replace("#", "").split("/")[0];
  if (name === "setup" || name === "connect") return name;
  return "simple";
}

// One place sets the Simple phase and keeps the URL with it (#simple, #simple/making, #simple/result,
// #simple/showcase), so the browser's Back button, the breadcrumb and the logo agree on where you are.
// "result" and "showcase" push a history entry; "making" and "choose" replace the current one, so Back
// from a finished video lands on the song screen, never on a dead making screen.
function setEasyPhase(phase) {
  if (!state || !state.easy) return;
  state.easy.phase = phase;
  if (phase === "showcase") state.easy.showcase = true;
  else if (phase !== "result") state.easy.showcase = false;
  const want =phase === "making" || phase === "result" || phase === "showcase" ? `#simple/${phase}` : "#simple";
  if (location.hash === want) return;
  try {
    if (phase === "result" || phase === "showcase") history.pushState(null, "", want);
    else history.replaceState(null, "", want);
  } catch (err) {
    location.hash = want.slice(1);
  }
}

// The phase from the URL after Back, Forward or a reload. A running job keeps the making screen whatever
// the URL says, and "making" is never re-entered from the URL alone (the job that was running is gone).
function easyPhaseFromHash() {
  if (!state || !state.easy) return;
  const sub = (location.hash || "#simple").replace("#", "").split("/")[1] || "";
  const running = !!(state.job && state.job.status === "running");
  if (running) {
    state.easy.phase = "making";
    return;
  }
  if (sub === "showcase") {
    state.easy.showcase = true;
    state.easy.phase = "showcase";
    return;
  }
  state.easy.showcase = false;
  const haveVideo = !!((state.job && state.job.video) || state.easy.playedHere || state.easy.reopenUrl);
  if (sub === "result" && haveVideo) {
    state.easy.phase = "result";
    return;
  }
  if (["making", "result", "showcase"].includes(state.easy.phase)) state.easy.phase = "choose";
  if (location.hash && location.hash !== "#simple") {
    try { history.replaceState(null, "", "#simple"); } catch (err) {}
  }
}

// Song › Vibe › Prototype › Refine › Share: the desk's stages, on every screen. Song and Vibe are the first screen,
// Prototype is the Make (a quick Draft and its making screen), Refine and Share are the cut's own screen (the timeline,
// the knobs, a Render of the whole song or at Final; then the files). A stage before the current one is a button back
// to it; on the cut's screen Share is a button down to its row.
function easyCrumbs(easy) {
  const phase = easy.phase || "choose";
  const video = phase === "result" || phase === "showcase";
  const making = phase === "making";
  const order = ["song", "vibe", "make", "refine", "share"];
  const labels = { song: "Song", vibe: "Vibe", make: "Prototype", refine: phase === "showcase" ? "Showcase" : "Refine", share: "Share" };
  const hints = {
    song: "Drop a track, use the bundled demo or pick a bundled song. The desk finds the beats, the sections and the drop.",
    vibe: "What everything is made of and how it is lit. Then one line: what you want to see, and how it should feel.",
    make: "A quick Draft of the cut, in minutes: the objects morph on every beat, lit by the song.",
    refine: "Fix what you do not like on the timeline (swap an object, hold a shot, change a handoff), re-cut without the GPU, then render at Final.",
    share: "Download the file, a 720p copy for a post, the 15 s hook, the recipe code.",
  };
  const cur = video ? "refine" : making ? "make" : !easy.song ? "song" : !easy.vibe ? "vibe" : "make";
  const tool = phase === "tool";  // on Setup or Connect: no stage is current, each one reachable is a way back
  const reach = tool ? order.indexOf(cur) + 1 : 0;
  const ci = tool ? -1 : order.indexOf(cur);
  const items = order.map((key, i) => {
    const ahead = key === "share" && phase === "result";  // the cut's screen holds Share too: a button down to it
    if ((i < ci && !making) || ahead || i < reach) return `<button type="button" class="crumb${i < ci ? " done" : ""}" data-act="easy-crumb" data-step="${key}" title="${esc(hints[key])}">${labels[key]}</button>`;
    return `<span class="crumb${i === ci ? " now" : ""}${i < ci ? " done" : ""}"${i === ci ? ' aria-current="step"' : ""} title="${esc(hints[key])}">${labels[key]}</span>`;
  });
  return `<nav class="easy-crumbs" aria-label="Where you are">${items.join('<span class="crumb-sep" aria-hidden="true">›</span>')}</nav>`;
}

// Ctrl+Enter (Cmd+Enter on a Mac) makes: the Make button says so, as desktop software does
function shortcutLabel() {
  const mac = /Mac|iPhone|iPad/.test((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "");
  return mac ? "⌘↵" : "Ctrl ↵";
}

// The last session's vibe and Fine-tune choices survive a reload or a desk restart (the song cannot: uploads live on the server).
const EASY_SAVED_KEYS = ["vibe", "idea", "energyPreset", "aspect", "tier", "fx", "endCard", "danceFx", "stemOrbit", "lengthS", "performer", "performerStyle", "gpuTier", "ownFolder", "vertical", "morphs", "ownShapes", "foreshadow", "scenes", "pins", "feelSig", "batchN", "batchVary", "morphSource", "scenesChosen", "morphStyle", "morphTiming", "effects"];
// The Model row's tiers as the desk names them (quality_tier: draft, fast, final, cloud)
const TIER_LABEL = { draft: "Draft", fast: "Fast Final", final: "Final", cloud: "Cloud Final" };
function saveEasy() {
  if (!state || !state.easy) return;
  try {
    const out = {};
    EASY_SAVED_KEYS.forEach((key) => { if (state.easy[key] !== undefined) out[key] = state.easy[key]; });
    localStorage.setItem("xeno-easy", JSON.stringify(out));
  } catch (err) {}
}
function loadEasy() {
  try {
    const saved = JSON.parse(localStorage.getItem("xeno-easy") || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch (err) {
    return {};
  }
}

function clock(seconds) {
  const safe = Math.max(0, seconds);
  const m = Math.floor(safe / 60);
  const s = Math.floor(safe % 60);
  const tenth = Math.floor((safe % 1) * 10);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${tenth}`;
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
    // Cloud Final spends Comfy Cloud credits: only the tick under Model sends it (cloud_final)
    cloud_final_ok: !!(state.easy && state.easy.tier === "cloud" && state.easy.cloudFinalOk),
    vertical_mode: (state.easy && state.easy.vertical) || "auto",
    morph_count: (state.easy && state.easy.morphs) || "auto",
    beat_fx: !(state.easy && state.easy.fx === false),
    end_card: !!(state.easy && state.easy.endCard),
    // The house look (demo_house): dance_fx "auto" | "off" | a preset; stem_orbit on unless switched off.
    dance_fx: (state.easy && state.easy.danceFx) || "auto",
    foreshadow: (state.easy && state.easy.foreshadow) || "auto",
    // how each morph changes (xenoform.morph_style): Auto or one style for all; Render at Final carries the prototype's
    // style a shot (carryStyles, set by that button only)
    morph_style: (state.easy && state.easy.morphStyle) || "auto",
    morph_styles: (state.easy && state.easy.carryStyles) || null,
    // when the change happens inside each morph (xenoform.morph_timing): smooth, beat or snap; a re-cut changes it
    morph_timing: (state.easy && state.easy.morphTiming) || "smooth",
    // the effects (xenoform.effects) and the blocky smear: a re-cut changes them too
    effects: (state.easy && state.easy.effects) || [],
    // Scenes (stills.kind "scene"): "off" (objects only), "mix" (a scene at every passage change), "only" (scenes alone)
    scene_stills: (state.easy && state.easy.scenes) || "off",
    // a Scenes choice made by hand: Off then stays Off when the idea line names a place (idea.shape_state)
    scenes_chosen: !!(state.easy && state.easy.scenesChosen),
    // The Chain row's pins: chain slot -> still file; the pick holds them and fills the rest (morph_pass.pins_of)
    chain_pins: (state.easy && state.easy.pins) || {},
    stem_orbit: !(state.easy && state.easy.stemOrbit === false),
    macros: (window.XENO_MACROS ? window.XENO_MACROS() : null),
    length_s: easyLength(state.easy),
    hardware_tier: (state.easy && state.easy.gpuTier) || "auto",
    performer: Number((state.easy && state.easy.performer) || 0),
    performer_style: (state.easy && state.easy.performerStyle) || "auto",
    // Your own clips and images (Simple): a folder on this machine, or the files dropped on the desk (own_id)
    own_folder: (state.easy && state.easy.ownFolder) || "",
    own_shapes: (state.easy && state.easy.ownShapes) || "",  // the shapes typed in Your own shapes: they lead this cut (morph_pass.pick_stills)
    own_id: (state.easy && state.easy.ownId) || "",
    // the clips in that folder are cut in only with Work in progress > Your clips on; the images always lead the chain
    morph_source: morphSource(state.easy),  // objects or your clips, never both in one cut (xenoform.clip_cut)
    // (the Director desk's scene_transitions rows are gone: the engine never read them, and the transition guard
    // reported one clamp line per boundary from them; per-boundary dressing is the timeline's, on the re-cut)
    idea:(state.easy && state.easy.idea) || "",
    song: (state.easy && state.easy.songLabel) || "",
    cut_plan: (state.easy && (state.easy.cloud || state.easy.remixPlan) && (state.easy.cutPlan || state.easy.remixPlan)) || null,
    // (no video_model: the tier picks the engine; the Final is LTX-2.5 wherever its files are installed, LTX-2.3 otherwise)
    brief: state.brief || "",
    mode: "simple",  // one desk, one engine: every Make is the Simple cut (dense.run_simple)
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
      dance_fx: scene.dance_fx || "",
      still_name:scene.still_name || "",
      reference_url: scene.reference_url || "",
    })),
    only_scenes: state.textOnly ? state.onlyScenes || [] : [],
    energy: Number(state.energy || 0),
    continuous: !!state.continuous,
    hero_id: state.heroId || "",  // Performer → Your own still (the server hands it to Polly's shots as hero_path)
    // (no title_card / end_card text here any more: the Director desk's text, sent after the End card switch above,
    // overwrote it with "", so End card On never reached a Make)
    motif:state.motif || "",
    callback: state.callback || "",
    climax: state.climax == null ? null : state.climax,
    treatment: state.treatment || "",
    guide_id: state.guideId || "",
    interpolate: !!state.interpolate,
  };
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
  // the note and the button follow the status line: once the port answers there is nothing left to start
  const portNote = status.running ? "The agent port is answering on this machine; paste a snippet below. It listens only on this machine and needs no token."
    : "The agent port is off until you start it, listens only on this machine, and needs no token.";
  return `<section class="panel connect">
    <p class="kicker">Agent</p>
    <h2>Connect an AI</h2>
    <p class="note">Grok, Claude, GPT, or Cursor can direct this desk. ${esc(portNote)} The desk it talks to is ${esc(snippets.desk)}.</p>
    <p class="mcp-status" id="mcp-status" data-running="${status.running ? "yes" : "no"}">${esc(status.detail || "")}</p>
    <div class="review-actions">
      <button type="button" class="ghost" data-act="mcp-test">Test connection</button>
      <button type="button" class="generate${state.mcpBusy ? " is-loading" : ""}" data-act="mcp-start"${state.mcpBusy || status.running ? " disabled" : ""}>${status.running ? "Running" : "Start on this machine"}</button>
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
  {"id": "botanical", "name": "Bloom timelapse", "line": "A single bloom on black, scrubbed by the song.", "palette": "natural", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/botanical.jpg", "featured": true},
  {"id": "none", "name": "None", "line": "No vibe: the things as they are, their own materials, plain light, no grade.", "palette": "neutral", "register": "pynchon", "morph": true, "dark": true, "tone": "dark", "still": "/static/vibes/none.jpg", "featured": true}
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
  const rows = VIBES.filter((vibe) => {
    if (which === "legacy") return !!vibe.legacy && vibe.id !== easy.vibe;
    return !vibe.legacy || vibe.id === easy.vibe;
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

// The originals and the non-featured registry vibes, behind one drawer under the featured twelve.
function moreVibes(easy) {
  const legacy = VIBES.filter((vibe) => vibe.legacy && vibe.id !== easy.vibe);
  if (!legacy.length) return "";
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

// The showcase's side column: it is not his render, so no knobs, no re-cut, no share. One way on.
function showcaseAside() {
  return `<aside class="panel easy-side">
        <h3>Make your own</h3>
        <p class="note">This reel was made earlier with the same engine. Back to the song, pick a vibe, then Make: a 30 s cut takes a few minutes on a 12 GB GPU, a full song about twenty.</p>
        <button type="button" class="generate easy-row" data-act="easy-again">Back to the song</button>
      </aside>`;
}

// Share, the last stage: the files of this cut under its timeline. Download (in the head) is the file itself at full
// quality; Share cut is a 720p H.264 under 16 MB for a post; then the hook, the recipe code, the shot list and the seed
// file the render wrote beside the cut (VJ mode is in Work in progress).
function shareRow(easy) {
  const id = easyVideoId();
  if (!id || easy.playedHere) return "";
  const job = encodeURIComponent(id);
  return `<section class="easy-share" id="easy-share" data-tour="easy-share">
      <div class="step-head"><h3>Share</h3><span>The files of this cut</span></div>
      <div class="share-row">
        <button type="button" class="ghost" data-act="easy-share" title="A 720p H.264 under 16 MB, for a post">Share cut · 720p</button>
        <button type="button" class="ghost" data-act="easy-hook" title="Cuts the strongest drop into a 15 second clip, same aspect and FX">15 s hook</button>
        <button type="button" class="ghost" data-act="easy-edit" title="The cut as a timeline for DaVinci Resolve, Premiere or Final Cut: a clip a shot, the song under it, markers at the drop, zipped with the media">Edit in Resolve</button>
        <button type="button" class="ghost" data-act="easy-copy-recipe">Copy recipe code</button>
        <a class="ghost" href="${esc(media(`/api/jobs/${job}/notes`))}" target="_blank" rel="noopener" title="Every shot with its time, object and transition (SHOTS.md)">Shot list</a>
        <a class="ghost" href="${esc(media(`/api/jobs/${job}/seed`))}" download="xenoform-${esc(id)}-seed.json" title="The seeds and settings the render used">Seed file</a>
      </div>
      ${easy.hookUrl ? `<p class="note">15 s hook ready: <a href="${esc(media(easy.hookUrl))}" download>download the hook</a>${easy.hookInfo ? ` · ${esc(easy.hookInfo)}` : ""}</p>` : ""}
      ${easy.editBusy ? `<div class="edit-ready"><b>Laying the cut out as a timeline…</b><span class="note">a few seconds: every shot is copied beside the song</span></div>` : ""}
      ${easy.editUrl && !easy.editBusy ? `<div class="edit-ready">
        <b>${easy.editOpened ? `The edit pack is open in Explorer, ${esc(easy.editTimeline || "the timeline file")} selected.` : "The edit pack is ready."}</b>
        <ol class="edit-steps"><li>In Resolve: File › Import › Timeline…</li><li>Pick <code>${esc(easy.editTimeline || "the .xml")}</code>${easy.editOpened ? " in the folder that just opened" : " from the zip"}</li><li>Leave “Automatically import source clips” on: every shot lands on V1, the song on A1, the markers on the drop</li></ol>
        <div class="share-row"><button type="button" class="ghost" data-act="easy-edit-open">Open the folder again</button><a class="ghost" href="${esc(media(easy.editUrl))}" download>Download the zip</a></div>
        ${easy.editInfo ? `<p class="note">${esc(easy.editInfo)}</p>` : ""}
      </div>` : ""}
      ${easy.recipe ? `<p class="note recipe-line">Recipe <code>${esc(easy.recipe)}</code></p>` : ""}
    </section>`;
}

// Render, after the prototype: the same vibe, idea line, chain pins, knobs and Fine-tune, made again for the whole song
// or at Final. It is a new render; the timeline's shot edits stay with the cut they were made on.
function renderRow(easy) {
  if (easy.showcase || (easy.playedHere && !easy.failed)) return "";
  const songSecs = easySongSeconds();
  const part = Number(easy.madeLength) > 0 && songSecs > Number(easy.madeLength) + 1;
  // a Final or a Cloud Final is already full size; a Draft or a Fast Final is offered the Final
  const draft = !["final", "cloud"].includes(easy.madeTier || "draft");
  if (!part && !draft && !easy.failed) return "";
  const noSong = !easy.song;
  const off = noSong ? " disabled" : "";
  const buttons = [
    easy.failed ? `<button type="button" class="generate easy-row" data-act="easy-make"${off}>Make it again</button>` : "",
    part ? `<button type="button" class="generate easy-row" data-act="easy-render-full"${off}>Render the whole song · ${esc(clockText(songSecs))}</button>` : "",
    draft ? `<button type="button" class="ghost easy-row" data-act="easy-render-final"${off} title="${esc(finalEtaText())}">Render at Final${part ? ` · these ${esc(String(easy.madeLength))} s` : ""}</button>` : "",
  ].join("");
  // the GPU cost per second of video as measured on this machine (took.json beside every Final, batch.measured), not a
  // guess: the old "roughly 90 s" was a sixth of the 600 s the 12 s demo's Final took on the 3080 Ti (27 Oct)
  const fin = state.simpleOptions && state.simpleOptions.final;
  const cost = fin && Number(fin.per_s) > 0
    ? `about ${clockText(Number(fin.per_s))} of GPU per second of video here (measured on ${fin.cuts} Final cut${fin.cuts === 1 ? "" : "s"})`
    : "minutes of GPU per second of video on a 12 GB card";
  const note = noSong
    ? "The song is not loaded in this window (uploads live on the desk until it restarts): choose it again on the first screen to render."
    : `A new render with this vibe, your line and the knobs. Final keeps this cut's objects in the same order (its chain is pinned) and is LTX-2.5 (LTX-2.3 where its files are missing) at full size, ${cost}. Handoff edits on this timeline stay with this cut: make them again on the sharp one.${easy.madeTier === "cloud" ? " This cut was a Cloud Final: a new render spends credits again, so go Back to the song and tick the credits box under Model in Fine-tune first." : ""}`;
  return `<div class="energy-head render-head"><h3>Render</h3><span>${part ? "The prototype becomes the video" : "The sharp version"}</span></div>
      ${buttons}
      <p class="note">${esc(note)}</p>`;
}

function renderEasy() {
  const easy = state.easy || { phase: "choose", song: "", vibe: "", idea: "", note: "" };
  const chosen = vibeById(easy.vibe) || VIBES[3];
  if (easy.phase === "making") {
    const width = Math.round(((state.job && state.job.progress) || 0.08) * 100);
    const scenes = state.scenes || [];
    // the chain this Make morphs through, not the Director storyboard: a Simple cut never renders the storyboard, and
    // "The rocket climbs past the bulb" under a cosmic cut read as a promise (26 Oct). The render's own chain
    // (job.chain, simple/chain.json once the line's stills are grown) wins over the Chain row's pre-Make preview, which
    // never shows what Make grows for the line (the rally car of "car rally race", 28 Oct).
    const made = state.job && Array.isArray(state.job.chain) && state.job.chain.length ? state.job.chain : null;
    // a clips cut has no object chain to preview: its own clips list arrives with job.chain
    const preview = morphSource(easy) === "clips" ? null : state.chain && state.chain.data && !state.chain.data.error && state.chain.data.stills;
    const chainStills = made || preview || [];
    const chainLine = chainStills.map((s) => s.noun || "").filter(Boolean).join(" \u2192 ");
    const story = chainLine || (easy.idea ? `Your line: ${easy.idea}` : chosen.line);
    const clipsCut = morphSource(easy) === "clips";
    const storyLabel = !chainLine ? (clipsCut ? "Your clips" : "The idea")
      : clipsCut ? `Your clips: ${chainStills.length} stretches, ${Math.max(0, chainStills.length - 1)} morphs between them`
      : `The chain${made ? "" : " (preview: Make may grow more for your line)"}: ${chainStills.length} stills, ${Math.max(0, chainStills.length - 1)} morphs`;
    const lineRead = ideaReading();  // what the line asked for, under the chain (the scenes it grows, Polly)
    const lineNote = lineRead && lineRead.summary ? `<p class="note">Your line, read: ${esc(lineRead.summary)}</p>` : "";
    const heard = easy.song ? "done" : "now";
    const wrote = scenes.length ? "done" : "now";
    const painting = scenes.length ? "now" : "wait";
    return `<div class="easy easy-making">
      <div class="easy-make-head">
        <div>
          <p class="eyebrow">${esc(chosen.name)} · ${esc(easy.songLabel || "Song")}${easy.madeLength ? ` · ${esc(String(easy.madeLength))} s prototype` : ""}${easy.madeTier && easy.madeTier !== "draft" ? ` · ${esc(TIER_LABEL[easy.madeTier] || easy.madeTier)}` : ""}</p>
          <h2>${easy.madeLength ? "Making the prototype." : "Making your video."}</h2>
        </div>
        <div class="easy-make-actions">
          <span id="easy-eta" aria-live="polite">${esc(easyEtaText())}</span>
          <button type="button" class="ghost" data-act="easy-stop">Stop</button>
        </div>
      </div>
      <div class="easy-make-grid">
        <div>
          <div class="monitor"${clipsCut ? "" : ` style="background-image:url(${esc(media(chosen.still))})"`}>
            <span class="monitor-pill">${esc(scenes.length ? `Shot 1 of ${scenes.length}` : "Reading the song")}</span>
          </div>
          ${clipsCut ? "" : `<div class="filmstrip">${shotStrip(chosen.id)}</div>`}
          <div class="track" aria-hidden="true"><span style="width:${width}%"></span></div>
        </div>
        <aside class="panel">
          <h3>What is happening</h3>
          <ol class="happen" id="easy-happen">
            <li class="${heard}">Listened to the song</li>
            <li class="${wrote}">Wrote the story</li>
            <li class="${painting}">Painting the shots</li>
            <li class="wait">Cutting to the beat</li>
          </ol>
          <p class="eyebrow" id="easy-chain-label">${esc(storyLabel)}</p>
          <p id="easy-chain">${esc(story)}</p>
          ${lineNote}
          <p class="note" id="easy-progress">${esc(easy.note || "Reading the song.")}</p>
          <p class="note">You can leave this page. The video keeps going and waits for you.</p>
        </aside>
      </div>
    </div>`;
  }
  if (easy.phase === "result" || easy.phase === "showcase") {
    const showcase = easy.phase === "showcase" || !!easy.showcase;
    const made = vibeById(easy.resultVibe || easy.vibe) || chosen;  // the cut's own vibe, whatever card is selected under Try another vibe
    const title = showcase ? "A finished one" : made && easy.vibe ? made.name : "Your cut";
    const another = !showcase && easy.vibe && easy.resultVibe && easy.vibe !== easy.resultVibe && chosen
      ? `<button type="button" class="generate easy-row" data-act="easy-make">Make it with ${esc(chosen.name)}</button>`
      : "";
    const actions = showcase
      ? `<button type="button" class="generate" data-act="easy-again">Make your own</button>
            <button type="button" class="ghost" data-act="easy-download">Download the showcase</button>`
      : `<button type="button" class="generate" data-act="easy-download">Download</button>`;
    const proto = !showcase && Number(easy.madeLength) > 0;
    return `<div class="easy easy-done">
      <section class="easy-result">
        <div class="easy-result-head">
          <div>
            <p class="eyebrow">${showcase ? "Showcase · made earlier" : proto ? `Prototype · ${esc(String(easy.madeLength))} s around the drop` : "Your video"}</p>
            <h2>${esc(title)}</h2>
          </div>
          <div class="easy-result-actions">
            <button type="button" class="ghost easy-back" data-act="easy-again">&larr; Back to the song</button>
            ${actions}
          </div>
        </div>
        <div class="player">
          ${easyMedia()}
          <button type="button" class="play-toggle" data-act="easy-play" aria-label="Play">Play</button>
          <p class="ready-toast">Your video is ready.</p>
        </div>
        <p class="note" id="easy-note">${esc(easy.note || "")}</p>
        <div id="easy-guard">${showcase ? "" : guardDetails(state.job)}</div>
        ${shotsLane(easy)}
        ${showcase ? "" : shareRow(easy)}
      </section>
      ${showcase ? showcaseAside() : `<aside class="panel easy-side" data-tour="easy-refine">
        <button type="button" class="knobs-fold" data-act="easy-knobs-fold" title="Fold the knobs away and give the video and the timeline the width; click again to bring them back" aria-label="Fold the knobs away">${knobsFolded() ? "‹ Knobs" : "Hide ›"}</button>
        <div class="energy-head"><h3>Knobs</h3><span>Turn, then re-cut. No GPU.</span></div>
        <div class="simple-knobs"></div>
        ${timingRow(easy.morphTiming || "smooth", "easy-morph-timing")}
        ${effectsRow(easy.effects, "easy-effect")}
        ${lookRow(easy.danceFx || "auto", "easy-look")}
        ${(state.lane && state.lane.source === "clips") || morphSource(easy) === "clips" ? "" : `${foreshadowRow(easy)}${scenesRow(easy)}<p class="note">Scenes applies to the next render, not the re-cut: a re-cut keeps this cut's stills.</p>`}
        <button type="button" class="generate easy-row" data-act="easy-recut-knobs"${easy.showcase || !easyVideoId() ? " disabled" : ""}>${pendingCount(easy) ? `Apply ${pendingCount(easy)} change${pendingCount(easy) === 1 ? "" : "s"}` : "Re-cut with these knobs"}</button>
        <p class="note">Re-composes the same morphs with the knobs, the look and the orbit as they are now, and with the timeline's edits. No GPU, no new pictures: a fraction of the render time.</p>
        ${renderRow(easy)}
        <div class="energy-head"><h3>Try another vibe</h3><span>Same song, same line</span></div>
        <div class="vibe-grid vibe-mini" role="radiogroup" aria-label="Try another vibe">${vibeCards(easy, true)}</div>
        ${another}
        ${easy.cloudPlan ? cloudCard(easy.cloudPlan) : ""}
        <button type="button" class="text easy-row" data-act="easy-again">Back to the song</button>
      </aside>`}
    </div>`;
  }
  const preview = easy.vibe ? chosen : VIBES[3];
  const songSet = !!easy.song;
  const songBlock = songSet
    ? `<div class="songrow">
        <span class="play-dot" aria-hidden="true">▶</span>
        <div><strong>${esc(easy.songLabel || "Chosen")}</strong><span>${esc(songFacts() || "Ready")}</span>${stemsLine()}</div>
        ${waveBars()}
      </div>`
    : `<div class="easy-actions">
        <label class="upload solid">Choose a song<input id="easy-file" type="file" accept="audio/*,.wav,.mp3,.flac,.ogg" aria-label="Choose a song" /></label>
        <button type="button" class="ghost${easy.song === "demo" ? " on" : ""}" data-act="easy-demo">Bundled demo</button>
      </div>
      <div id="bundled-songs">${songsRow(easy)}</div>`;
  const proto = easyLengthIsProto(easy);
  return `<div class="easy easy-desk">
    <header class="easy-intro">
      <h2>Make a music video.</h2>
      <p class="lede">One object keeps transforming into the next, every change on the beat. A song and a vibe make a quick prototype; refine it on its timeline, then render the whole song or Final. Free, local, open weights.</p>
    </header>
    <section class="easy-main">
      <section class="easy-step" data-tour="easy-song" data-song-drop="1">
        <div class="step-head"><h3>Song</h3>${songSet ? '<button type="button" class="text" data-act="easy-step" data-step="song">Change</button>' : ""}</div>
        ${songBlock}
        ${songSet ? "" : `<p class="note">${esc(easy.songLabel || "Drop a file here, use the bundled demo, or pick one of the bundled songs.")}</p>`}
        ${dropCard()}
      </section>
      <section class="easy-step" data-tour="easy-vibe">
        <div class="step-head"><h3>Vibe</h3><span>Pick one. You can try another after.</span></div>
        <div class="vibe-grid" role="radiogroup" aria-label="Vibe">${vibeCards(easy, false, "featured")}</div>
        ${moreVibes(easy)}
        ${sourceRow(easy)}
        ${morphSource(easy) === "objects" ? ideaBlock(easy) : ""}
      </section>
      <section class="panel span simple-knobs-panel" data-tour="easy-macros">
        <h3>Knobs</h3>
        <p class="note">Intensity is the beat pulse and flash. Speed is the cut density and the trail length. Chaos is the punches, stutters and how far the subject swings, and it wilds the cuts: wipes and chromatic rips at the handoffs as it climbs (the blocky smear too, sparingly, when Effects asks for it), strobe cuts past 0.7 (never two in two seconds), plain cuts at 0. Glow is the bloom. The look rides the vibe's own colours unless you pick one.</p>
        <div class="simple-knobs"></div>
        ${morphStyleRow(easy.morphStyle || "auto", "easy-morph-style")}
        <p class="note morph-style-note">${esc(MORPH_STYLE_NOTES[easy.morphStyle || "auto"] || "")}</p>
        ${timingRow(easy.morphTiming || "smooth", "easy-morph-timing")}
        <p class="note morph-timing-note">${esc(MORPH_TIMING_NOTES[easy.morphTiming || "smooth"] || "")}</p>
        ${effectsRow(easy.effects, "easy-effect")}
        ${lookRow(easy.danceFx || "auto", "easy-look")}
        ${morphSource(easy) === "objects" ? `${foreshadowRow(easy)}${scenesRow(easy)}` : ""}
        <p class="note look-note">${esc(lookNote(easy.danceFx || "auto"))}</p>
      </section>
      ${fineTune(easy)}
      ${wipDrawer(easy)}
      ${galleryPanel()}
    </section>
    <aside class="panel easy-side" data-tour="easy-make">
      <div class="monitor" style="background-image:url(${esc(media(preview.still))})"><span class="monitor-pill">${esc(preview.name)} · sample</span></div>
      <div class="filmstrip">${shotStrip(preview.id)}</div>
      <dl class="facts">
        ${easyPlanFacts(easy)}
      </dl>
      <button type="button" class="generate easy-make" data-act="easy-make"><span>${proto ? `Make a ${esc(String(easyLength(easy)))} s prototype` : "Make my video"}</span><kbd>${esc(shortcutLabel())}</kbd></button>
      <p class="note house-line">${proto
        ? `A ${esc(TIER_LABEL[easy.tier] || "Draft")} of ${esc(String(easyLength(easy)))} s around the drop, in minutes. Then refine it, and render the whole song or Final from its screen. Fine-tune → Length makes the whole song now.`
        : `${esc(easy.aspect || "9:16")}, ${(easy.energyPreset || "dense") === "dense" ? "Dense" : "Flow"}, ${esc(TIER_LABEL[easy.tier] || "Draft")}, Beat FX and the house look. Fine-tune below the vibes if you want to; Final is one press on the cut's screen.`}</p>
      ${variationsRow(easy)}
      ${easy.cloudPlan ? cloudCard(easy.cloudPlan) : ""}
      <button type="button" class="ghost easy-showcase" data-act="easy-showcase">Watch a finished one · plays now</button>
      <p class="note" id="easy-note">${esc(easy.note || "No ComfyUI? It plays in your browser.")}</p>
      <p class="note tools-line"><button type="button" class="text" data-act="go" data-hash="setup">Setup &amp; models</button></p>
      <p class="side-foot"><a class="ow-badge" href="${esc(media("/licences"))}" title="LTX-2.3 has a revenue threshold. FLUX.2 Klein 9B is non-commercial. This desk uses the Apache 2.0 4B.">Open weights</a></p>
    </aside>
  </div>`;
}

// Variations (xenoform.batch, from Pause's "Thirty nights. Thirty uploads."): several Drafts of this idea queued for the
// night, each varying one thing, run one at a time on a free GPU and compared on /variations in the morning. The time is
// what a Draft this long took on this machine (GET /api/batches?seconds=, the took.json beside every cut).
const VARY_NOTES = {
  seed: "Each one keeps your settings and rolls new dice: other objects from the library, other morphs, other handoffs.",
  vibe: "Each one is your line in another vibe (another material and light), one vibe each.",
  feel: "Each one is your line with another feel (slow and dreamy, hard and glitchy, warm and hazy...): its knobs and its Look.",
};
function spanText(seconds) {
  const m = Math.max(1, Math.round(Number(seconds || 0) / 60));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
}
function variationsRow(easy) {
  const n = Number(easy.batchN) || 3;
  const vary = easy.batchVary || "seed";
  const seconds = easyLength(easy) || easySongSeconds();
  const rates = state.batchRates && state.batchRates.seconds === seconds ? state.batchRates.measured : null;
  if (!rates && state.batchRatesFor !== seconds) loadBatchRates(seconds);
  const each = rates && rates.draft && Number(rates.draft.eta_s);
  const time = each ? ` · about ${spanText(n * each)}` : "";
  const measured = each ? ` A Draft this long takes about ${spanText(each)} here (${rates.draft.cuts} cuts measured)${rates.final ? `; the last Final, ${Math.round(rates.final.latest.seconds)} s, took ${spanText(rates.final.latest.took_s)}` : ""}.` : "";
  // Variations are extra Drafts queued for later, separate from Make: they never make Make slower or faster. One is a
  // Draft of the settings as they are, run when the GPU is free (nothing varies, so the second row hides).
  return `<div class="variations-row" data-tour="easy-variations">
      <p class="note">Queue Drafts to render later, one after another, while you do something else. Make is not affected.</p>
      ${simpleSeg("easy-batch-n", String(n), [["1", "1"], ["3", "3"], ["5", "5"], ["10", "10"]], "How many")}
      ${n > 1 ? simpleSeg("easy-batch-vary", vary, [["seed", "New objects"], ["vibe", "Other vibes"], ["feel", "Other feels"]], "What changes") : ""}
      <button type="button" class="ghost easy-row" data-act="easy-batch">Queue ${n} Draft${n === 1 ? "" : "s"}${esc(time)}</button>
      <p class="note">${n > 1 ? esc(VARY_NOTES[vary] || "") : "One Draft of your settings as they are, started as soon as nothing else is rendering."} ${n > 1 ? "They run one after another and wait for any other render, so leave them overnight." : ""}${esc(measured)} <a href="/variations" target="_blank" rel="noopener">Compare them &rarr;</a></p>
    </div>`;
}
async function loadBatchRates(seconds) {
  state.batchRatesFor = seconds;
  try {
    const res = await api(`/api/batches?seconds=${encodeURIComponent(seconds)}`);
    const data = await res.json();
    if (res.ok && state) {
      state.batchRates = { seconds, measured: data.measured || {} };
      render();
    }
  } catch (err) {
    // the row reads without a time
  }
}
async function easyBatch(button) {
  const vibe = vibeById(state.easy.vibe);
  const n = Number(state.easy.batchN) || 3;
  const vary = state.easy.batchVary || "seed";
  if (!vibe || !state.easy.song) {
    state.easy.note = "Choose a song and a vibe, then queue the variations.";
    render();
    return;
  }
  if (button) button.classList.add("is-loading");
  await refreshComfy();
  if (!state.comfyOk) {
    if (button && button.isConnected) button.classList.remove("is-loading");
    state.easy.note = "ComfyUI is not answering, and variations are renders. Start it, then queue them.";
    render();
    return;
  }
  // the body a Make would send (easyMake's own preparation, without the making screen), at Draft
  const tier = state.easy.tier;
  state.brief = (state.easy.idea || "").trim() || vibe.line;
  state.palette = vibe.palette;
  state.register = vibe.register;
  state.morphCap = vibe.morph ? 1 : 0;
  state.energy = energyFromTrack();
  state.continuous = false;
  state.quality = "live";
  await planStory();
  if (!state || !state.easy) return;
  state.quality = "turbo";
  state.live = true;
  state.easy.tier = "draft";
  const body = payload();
  state.easy.tier = tier;
  try {
    const res = await api("/api/batches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body, count: n, vary }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "The variations did not queue.");
    const left = Number(data.left_s) > 0 ? `, about ${spanText(data.left_s)} in all here` : "";
    state.easy.note = data.items.length === 1
      ? `One Draft queued${left}. It starts when nothing else is rendering: Compare them, under the button, shows it when it lands.`
      : `${data.items.length} Drafts queued, ${{ seed: "new objects", vibe: "another vibe", feel: "another feel" }[vary] || vary} in each${left}. They run one after another: Compare them, under the button, shows each as it lands.`;
  } catch (err) {
    state.easy.note = String(err.message || err);
  }
  render();
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
  const measured = info.eta_measured ? ` (measured here, ${info.cuts} Final cut${info.cuts === 1 ? "" : "s"})` : " (estimate, not yet measured on this card)";
  return `Final renders with LTX-2.5 when its files are installed, LTX-2.3 otherwise, at ${info.render}, upscaled to ${info.output}. About ${clockText(info.eta_s)}${measured}.${ready}`;
}

// Fine-tune: everything that is not song / vibe / Make, in one drawer that remembers whether it was open.
function fineTune(easy) {
  const open = readDrawer("xeno-finetune");
  if (easy.vibe && (!state.stills || state.stills.vibe !== easy.vibe) && !state.stillsLoading) {
    state.stillsLoading = true;
    setTimeout(() => { loadStills(true).finally(() => { state.stillsLoading = false; }); }, 0);
  }
  const bits = [easy.aspect || "9:16", (easy.energyPreset || "dense") === "dense" ? "Dense" : "Flow", TIER_LABEL[easy.tier] || "Draft",
    lookLabel(easy.danceFx || "auto"), easy.scenes && easy.scenes !== "off" ? `Scenes ${easy.scenes}` : ""].filter(Boolean);
  return `<details class="fine-tune" id="fine-tune"${open ? " open" : ""}>
      <summary>Fine-tune <small>${esc(bits.join(" · "))}</small></summary>
      ${simpleOptions(easy)}
      ${morphSource(easy) === "objects" ? `${ownRow(easy)}${stillsRow(easy)}${chainRow(easy)}` : ""}
      ${beatOverlayRow(easy)}
      ${remixBox(easy)}
    </details>`;
}

// Work in progress (docs/MORPH_ENGINE_PLAN.md §3, Tys 28 Oct: "everything else should be hidden behind a drop down tab
// and be 'work in progress'"): what is on the desk but is not the morph engine, in one closed drawer under Fine-tune.
// Each works as it did; it only lives here until it is finished.
function wipDrawer(easy) {
  const open = readDrawer("xeno-wip");
  const item = (title, why, body) => `<div class="wip-item"><h4>${esc(title)}</h4><p class="note">${esc(why)}</p>${body}</div>`;
  return `<details class="fine-tune wip-drawer" id="wip-drawer"${open ? " open" : ""}>
      <summary>Work in progress <small>Polly · cloud · Moves · VJ and MIDI · Connect an AI</small></summary>
      <p class="note wip-lede">Xenoform is the morph engine. These work, but they are not the engine and not finished, so they wait here.</p>
      ${item("Performer", "Polly sings, drums or dances to the song in a few shots of the cut (MiniMax H3). The idea line no longer brings her in: switch her on here.", performerRow(easy))}
      ${item("Paid cloud", "LTX-2.5 through a paid Comfy partner node: not open weights, off by default.", cloudRows(easy))}
      ${item("Live", "Character dances, live visuals to the stems, a MIDI controller on the knobs.",
        `<p class="note"><a href="/moves">Moves: make a character dance to a real dance clip (Wan Animate 2) &rarr;</a></p>
        <p class="note"><a href="${esc(vjUrl())}" target="_blank" rel="noopener">VJ mode: live visuals to this song's stems &rarr;</a> · <button type="button" class="text" data-act="easy-midi">MIDI controller</button></p>`)}
      ${item("Connect an AI", "Any AI drives the same desk over MCP.", `<button type="button" class="text" data-act="go" data-hash="connect">Connect an AI &rarr;</button>`)}
    </details>`;
}

// How each morph changes (xenoform.morph_style, docs/MORPH_ENGINE_PLAN.md E1): Auto, or one style for every morph of
// the cut. Melt is the liquid flow every morph had before; Shatter, Bloom, Spin and Fold read as their own on film (the
// 28 Oct Draft test). The timeline sets a shot's own, a re-render of that one morph.
const MORPH_STYLES = ["melt", "shatter", "bloom", "spin", "fold"];
const MORPH_STYLE_NOTES = {
  "auto": "Melt through the verses, Shatter on the drop; the opening Blooms, or with Chaos past 0.6 the builds Fold and the loud shots after the drop Spin.",
  "melt": "The object melts and flows into the next: one continuous liquid change.",
  "shatter": "The object cracks into shards that swirl and snap together as the next.",
  "bloom": "The object opens like a flower, and the next grows out of its centre.",
  "spin": "The object spins and changes shape as it turns: the most motion.",
  "fold": "The object folds like paper, its planes flipping into the next.",
};
function morphStyleLabel(id) {
  return id === "auto" || !id ? "Auto" : String(id).charAt(0).toUpperCase() + String(id).slice(1);
}
function morphStyleRow(current, act, index, auto = true) {
  const ids = (auto ? ["auto"] : []).concat(MORPH_STYLES);
  const chips = ids
    .map((id) => `<button type="button" class="chip${id === current ? " on" : ""}" data-act="${act}" data-value="${esc(id)}"${index == null ? "" : ` data-index="${index}"`} aria-pressed="${id === current ? "true" : "false"}" title="${esc(MORPH_STYLE_NOTES[id] || "")}">${esc(morphStyleLabel(id))}</button>`)
    .join("");
  return `<div class="simple-seg morph-style-row"><span>Morph</span><div class="toggle chips" role="group" aria-label="How each morph changes">${chips}</div></div>`;
}

// When the change happens inside each morph (xenoform.morph_timing, docs/MORPH_ENGINE_PLAN.md E2): the cached clip
// re-timed from its measured change, so a re-cut sets it with no GPU. The timeline gives a shot its own.
const MORPH_TIMINGS = ["smooth", "beat", "snap"];
const MORPH_TIMING_LABELS = { smooth: "Smooth", beat: "On the beat", snap: "Snap" };
const MORPH_TIMING_NOTES = {
  "smooth": "The morph plays at an even speed: the change happens wherever the model put it.",
  "beat": "The change moves in steps, fastest on every beat inside the shot, nearly still between them.",
  "snap": "The object holds, then changes in about a beat on the shot's downbeat; the drop snaps hardest.",
};
function timingRow(current, act, index, asCut) {
  const ids = (asCut ? ["auto"] : []).concat(MORPH_TIMINGS);
  const chips = ids
    .map((id) => {
      const label = id === "auto" ? `As the cut (${MORPH_TIMING_LABELS[asCut] || "Smooth"})` : MORPH_TIMING_LABELS[id];
      return `<button type="button" class="chip${id === current ? " on" : ""}" data-act="${act}" data-value="${esc(id)}"${index == null ? "" : ` data-index="${index}"`} aria-pressed="${id === current ? "true" : "false"}" title="${esc(MORPH_TIMING_NOTES[id] || "the cut's own timing")}">${esc(label)}</button>`;
    })
    .join("");
  return `<div class="simple-seg morph-timing-row"><span>Timing</span><div class="toggle chips" role="group" aria-label="When the change happens inside each morph">${chips}</div></div>`;
}

// TouchDesigner-style effects (xenoform.effects), any of them at once, after the Look and riding the kick and the
// loudness; a re-cut changes them with no GPU. "smear" is the blocky datamosh smear at a few handoffs, off unless asked.
const EFFECTS = ["dither", "feedback", "kaleido", "slitscan", "smear"];
const EFFECT_LABELS = { dither: "Dither hits", feedback: "Feedback", kaleido: "Kaleido", slitscan: "Slit-scan", smear: "Blocky smear" };
const EFFECT_NOTES = {
  "dither": "On each kick the picture drops to a few tones of the vibe's palette in fine blue-noise dots, then lets go.",
  "feedback": "The picture over a zoomed, turned copy of the frame before: bright objects leave a tunnel; it swells with the loudness.",
  "kaleido": "The frame folded into mirrored wedges, mixed in with the loudness, turning a step on each beat.",
  "slitscan": "Each row from a moment further back the lower it sits: motion bends into curves as the song gets loud.",
  "smear": "The blocky datamosh smear at a few handoffs (one in six at most, never the drop); off, those handoffs wipe or rip instead.",
};
function effectsRow(current, act) {
  const on = new Set(current || []);
  const chips = EFFECTS
    .map((id) => `<button type="button" class="chip${on.has(id) ? " on" : ""}" data-act="${act}" data-value="${esc(id)}" aria-pressed="${on.has(id) ? "true" : "false"}" title="${esc(EFFECT_NOTES[id] || "")}">${esc(EFFECT_LABELS[id])}</button>`)
    .join("");
  const picked = EFFECTS.filter((id) => on.has(id));
  const note = picked.length ? picked.map((id) => `${EFFECT_LABELS[id]}: ${EFFECT_NOTES[id]}`).join(" ") : "None: the morphs, the beat FX and the Look alone. Any of these can go on together.";
  return `<div class="simple-seg effects-row"><span>Effects</span><div class="toggle chips" role="group" aria-label="Effects">${chips}</div></div>
      <p class="note effects-note">${esc(note)}</p>`;
}

const LOOK_PRESETS = ["warm-leak", "cool-echo", "noir-glow", "bloom-rush", "negative-rush", "cyan-flash", "dither"];
const LOOK_NOTES = {
  "dither": "the vibe's palette in a few tones, broken up by fine blue-noise dots that jump on the beat (a print, a screen, a 1-bit game)",
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
  // the negative pulse flips the frame's luma: on a bright vibe (risograph, ink, porcelain, glass) it is softened to a
  // quarter by the look pass itself, and the chip says so; "off" on Draft shows the morphs' own held frames
  const vibe = state.easy && vibeById(state.easy.vibe);
  const bright = !!(vibe && (vibe.tone === "bright" || vibe.dark === false));
  const extra = (id) => (bright && (id === "negative-rush" || id === "cyan-flash")) ? " · the negative pulse is softened on a bright vibe"
    : (id === "off" ? " · with no look, Draft morphs show their held frames; the QA pass fills them" : "");
  const chips = ids
    .map((id) => `<button type="button" class="chip${id === current ? " on" : ""}" data-act="${act}" data-value="${esc(id)}"${index == null ? "" : ` data-index="${index}"`} aria-pressed="${id === current ? "true" : "false"}" title="${esc(lookNote(id) + extra(id))}">${esc(lookLabel(id))}</button>`)
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
    ? `MiniMax H3 (open weights, on this GPU) has Polly sing the intro and drum the drop, cut 1:1 into the morph chain. About ${clockText(Number(info.seconds_per_shot || 420))} a shot on a 12 GB card. The performer is Polly unless you give it your own full-body still below.`
    : `Off: ${esc(info.note || "the MiniMax H3 files are not installed")}. See Setup.`;
  const styles = [["auto", "Auto"], ["sing", "Sing"], ["drums", "Drums"], ["keys", "Keys"], ["guitar", "Guitar"], ["dance", "Dance"]];
  const styleRow = n ? simpleSeg("easy-performer-style", easy.performerStyle || "auto", styles, "Performance") : "";
  const styleNote = n ? `<p class="note">Auto: she sings where the song's vocal stem sings (lip-synced to the vocal), drums on the drop, keys elsewhere; she never mouths words that are not there.</p>` : "";
  // the performer's own still (POST /api/hero; it lived on the old Director desk): the make body's hero_id, Polly's
  // shots start from it instead of her posed stills (dense: performer_ref or hero_path)
  const own = n ? `<div class="simple-seg own-row performer-own"><span>Your own still</span>
      ${state.heroUrl ? `<img class="hero-thumb" alt="Your performer" src="${esc(media(state.heroUrl))}" />` : ""}
      <label class="ghost cloud-toggle">${state.heroUrl ? "Replace" : "Use"} a full-body still <input id="hero-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label>
      ${state.heroUrl ? `<button type="button" class="ghost" data-act="easy-hero-clear">Back to Polly</button>` : ""}
    </div>` : "";
  return `${simpleSeg("easy-performer", String(ok ? n : 0), choices, "Performer")}
      <p class="note">${note}</p>${styleRow}${styleNote}${own}`;
}

// Your own images: a folder on this machine, or files dropped or picked here. The images lead the vibe's morph chain
// (morph targets, in name order): morphing between your own pictures is the engine. Clips in the same folder are cut
// in on the beat only with Work in progress > Your clips on (one run of shots at the start of a passage, 2 to 8 s,
// trimmed around its middle and played 1:1 like a performer shot).
function ownRow(easy) {
  const note = easy.ownNote || "Your images lead the morphs, in name order. Leave empty and the vibe's own objects carry the cut. Clips are never cut into objects: for them, Morph > Your clips at the top.";
  return `<div class="simple-seg own-row" data-own-drop><span>Your images</span>
      <label class="ghost cloud-toggle">Folder <input type="text" id="easy-own-folder" value="${esc(easy.ownFolder || "")}" spellcheck="false" aria-label="Folder of your images" placeholder="a folder of images"></label>
      <label class="ghost cloud-toggle">Drop or pick files <input type="file" multiple accept="video/*,image/*" data-act="easy-own-files" hidden></label>
      ${easy.ownId ? `<button type="button" class="ghost" data-act="easy-own-clear">Clear files</button>` : ""}
    </div>
    <p class="note">${esc(note)}</p>`;
}

// The stills library: the objects this vibe's morphs travel between. The repo ships a seed set; Grow renders more
// on this GPU (Z-Image Turbo through ComfyUI, about 6 s a still), each checked against the vibe's own pool and kept
// under work/ui/objects. Your own shapes are typed subjects rendered in the vibe's material; they go first in the chain.
// The library row's two live lines: the vibe's counts and the running grow, both rewritten in place while a grow runs.
function stillsCount(easy) {
  const lib = state.stills || {};
  const have = (lib.counts || {})[easy.vibe] || { shipped: 0, grown: 0, own: 0, total: 0 };
  const vibe = vibeById(easy.vibe);
  const name = (vibe && vibe.name) || easy.vibe || "this vibe";
  const parts = [`${have.shipped} shipped`, `${have.grown} grown here`, have.own ? `${have.own} of your own` : "", have.scenes ? `${have.scenes} scenes` : ""].filter(Boolean);
  const left = lib.vibe === easy.vibe && lib.subjects_left != null ? ` · ${lib.subjects_left} subjects left to render` : "";
  return `${name}: ${parts.join(" · ")}${left}`;
}
function stillsStatus(easy) {
  const job = (state.stills || {}).job || {};
  if (job.status === "running" || job.status === "starting") {
    const eta = Number(job.eta_s || 0) - (Date.now() / 1000 - Number(job.started || 0));
    const left = eta > 0 ? `about ${clockText(eta)} left` : (job.done ? "finishing" : "loading the model, the first render takes longer");
    return `Growing ${job.kind === "scene" ? "scenes for " : ""}${job.vibe}: ${job.done || 0} of ${job.asked || 0} rendered · kept ${job.kept || 0} · ${left}`;
  }
  if (easy.stillsNote) return easy.stillsNote;
  if (job.status === "done" && job.note) return `${job.vibe}: ${job.note}`;
  if (job.status === "error" && job.note) return `Library: ${job.note}`;
  return "";
}
function stillsRow(easy) {
  const lib = state.stills || {};
  const job = lib.job || {};
  const running = job.status === "running" || job.status === "starting";
  const grow = Number(lib.default_grow || 36);
  const growScenes = Number(lib.default_grow_scenes || 8);
  const status = stillsStatus(easy);
  // the status sits on its own fixed line and the explanation never swaps for it, so the row keeps its height while a
  // grow runs; loadStills rewrites just this line every few seconds (stillsStatus) instead of redrawing the desk
  const note = `Every still is rendered on this GPU (Z-Image Turbo, about ${Math.round(Number(lib.seconds_per_still || 6))} s each), checked against the vibe's own pool (backdrop, size, cropped, soft, duplicate) and kept under the work folder; delete a jpg there to drop it. Your own shapes go first in the chain. Scenes are wide frames in the vibe's light (a dark shore, a corridor of mirrors); the Scenes row morphs them in.`;
  return `<div class="simple-seg own-row library-row"><span>Library</span>
      <span class="library-count" id="library-count">${esc(stillsCount(easy))}</span>
      <span class="library-status" id="library-status" aria-live="polite">${esc(status)}</span>
      <button type="button" class="ghost" data-act="easy-grow"${running || !easy.vibe ? " disabled" : ""} title="Render ${grow} new objects for this vibe on this GPU">Grow ${grow} more</button>
      <button type="button" class="ghost chip" data-act="easy-grow-scenes"${running || !easy.vibe ? " disabled" : ""} title="Render ${growScenes} wide scenes for this vibe on this GPU; the Scenes row below morphs them in">Grow ${growScenes} scenes</button>
      <label class="ghost cloud-toggle">Your own shapes <input type="text" id="easy-own-shapes" value="${esc(easy.ownShapes || "")}" spellcheck="false" aria-label="Your own shapes, comma-separated" placeholder="a brass astrolabe, a wolf skull"></label>
      <button type="button" class="ghost" data-act="easy-make-shapes"${running || !easy.vibe ? " disabled" : ""} title="Render the shapes you typed in this vibe's material">Make them</button>
      ${running ? '<button type="button" class="ghost" data-act="easy-grow-stop">Stop</button>' : ""}
    </div>
    <p class="note">${esc(note)}</p>`;
}

// The idea line, its reading and its help: what an object cut morphs through (a clips cut has no objects to name).
function ideaBlock(easy) {
  return `        <label class="idea-field">What it morphs through <small>optional · things, a theme, a place, a feel</small>
          <input id="easy-idea" type="text" maxlength="170" value="${esc(easy.idea || "")}" aria-label="What it morphs through, optional" placeholder="a nautilus, a jellyfish, an orchid, a moonlit shore, slow and dreamy" autocomplete="off" />
        </label>
        ${ideaReadingLine(easy)}
        <details class="idea-help"><summary>How the line works</summary>
          <p class="note">Commas split it. Things become the objects the morphs travel between: one the library knows brings its family along, one it lacks is drawn new in this vibe's material before Make. A theme (underwater, magic, dinosaurs, space, halloween and about thirty more) brings fifteen things of its own and keeps the chain on them. A place becomes wide scenes the morphs pass through. A feel (slow and dreamy, hard and glitchy) moves the knobs and the Look. It never changes the vibe, and it cannot tell a story: every shot is still one thing becoming the next. Empty, and the vibe decides.</p>
        </details>`;
}

// Objects or your clips (Tys, 28 Oct: "if we are going to morph movie clips, make it so its just movie clips, and if we
// are doing objects just objects"): what a Make morphs through. Your clips play in turn, each morphing into the next
// (xenoform.clip_cut); the idea line, the library, the Chain row, Scenes and Foreshadow belong to objects and step aside.
function morphSource(easy) {
  return easy && easy.morphSource === "clips" ? "clips" : "objects";
}
function sourceRow(easy) {
  const src = morphSource(easy);
  const seg = simpleSeg("easy-source", src, [["objects", "Objects"], ["clips", "Your clips"]], "Morph");
  if (src !== "clips") return `${seg}<p class="note">The vibe's objects, or the things your line names, each turning into the next.</p>`;
  const has = !!(easy.ownFolder || easy.ownId);
  const note = easy.ownNote || (has ? "Your clips play in turn on the beat, each its busiest stretch, and every one morphs into the next. No objects, no stills."
    : "Choose a folder of clips, drop them here (mp4, mov or webm, 2 s or more each), or take the free film pack. They play in turn, each morphing into the next.");
  const askSetup = !!note && note === easy.ownNoteSetup;  // the free film pack is not downloaded yet: the note points at Setup
  return `${seg}
    <div class="simple-seg own-row clips-row" data-own-drop><span>Your clips</span>
      <label class="ghost cloud-toggle">Folder <input type="text" id="easy-own-folder" value="${esc(easy.ownFolder || "")}" spellcheck="false" aria-label="Folder of your clips" placeholder="a folder of clips"></label>
      <label class="ghost cloud-toggle">Drop or pick files <input type="file" multiple accept="video/*" data-act="easy-own-files" hidden></label>
      <button type="button" class="ghost" data-act="easy-film-pack" title="Public-domain film clips from archive.org, downloaded in Setup &amp; models">Free film pack</button>
      ${easy.ownId ? `<button type="button" class="ghost" data-act="easy-own-clear">Clear files</button>` : ""}
    </div>
    <p class="note">${esc(note)}${askSetup ? ` <button type="button" class="text" data-act="go" data-hash="setup">Setup &amp; models</button>` : ""}</p>`;
}

// The Chain row: the stills this Make will morph through, in order, as the stills draft previews them
// (POST /api/simple/chain, dense.chain_preview: nothing rendered, nothing marked used). Click a slot and pick another
// object or scene from the vibe's library; a pinned slot holds through Make (the make body's chain_pins, which
// morph_pass.pick_stills honours slot by slot), the rest are picked fresh. The idea line, Scenes and Length move the picks.
// The idea line, read (POST /api/simple/idea, xenoform.idea): the scenes it names (grown before Make), the objects the
// library knows, the shapes it lacks, Polly when it names a dancer or singer. Shown under the line as it is typed.
let ideaTimer = null;
function ideaKey() {
  const e = state.easy || {};
  return JSON.stringify([e.vibe || "", String(e.idea || "").trim()]);
}
function scheduleIdea() {
  if (ideaTimer) clearTimeout(ideaTimer);
  ideaTimer = setTimeout(() => { ideaTimer = null; loadIdea(ideaKey()); }, 400);
}
async function loadIdea(key) {
  const e = state.easy || {};
  if (!String(e.idea || "").trim()) { state.ideaReading = { key, data: null }; paintIdeaReading(); return; }
  let data;
  try {
    const res = await api("/api/simple/idea", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idea: e.idea, vibe: e.vibe || "" }) });
    const body = await res.json().catch(() => ({}));
    data = res.ok ? body : { error: body.detail || "The line could not be read." };
  } catch (err) {
    data = { error: "The line could not be read." };
  }
  if (!state.easy || ideaKey() !== key) return;  // the line moved on; a newer request follows
  state.ideaReading = { key, data };
  applyFeel(data);
  paintIdeaReading();
}
// "slow and dreamy" in the line (xenoform.idea.feel_of): the knobs and the Look move to it once, when the feel words
// change, so a knob moved by hand afterwards stays where it was put (feelSig is saved with the desk's choices). The
// chips and knobs are painted in place: a render here would take the caret out of the line while it is typed.
function applyFeel(data) {
  const feel = data && !data.error ? data.feel : null;
  if (!feel || !state.easy) return;
  const sig = JSON.stringify([feel.words || [], feel.look || ""]);
  if (state.easy.feelSig === sig) return;
  state.easy.feelSig = sig;
  Object.entries(feel.macros || {}).forEach(([k, v]) => { if (window.XENO_MACRO_SET) window.XENO_MACRO_SET(k, Number(v)); });
  if (feel.look) {
    state.easy.danceFx = feel.look;
    document.querySelectorAll('[data-act="easy-look"]').forEach((chip) => {
      const on = chip.dataset.value === feel.look;
      chip.classList.toggle("on", on);
      chip.setAttribute("aria-pressed", on ? "true" : "false");
    });
    document.querySelectorAll(".look-note").forEach((note) => { note.textContent = lookNote(feel.look); });
  }
  saveEasy();
}
function ideaReading() {
  return state.ideaReading && state.ideaReading.key === ideaKey() && state.ideaReading.data && !state.ideaReading.data.error
    ? state.ideaReading.data : null;
}
// What the line became, as labelled chips a glance can read instead of a sentence (Tys, 28 Oct: "make that more
// intuitive without having to read a block of fine print"): what the morphs travel between, what they pass through, how
// it feels, who performs; "new" on what Make draws first. With the line empty, the same rows show what can go in it.
const IDEA_ROWS = [["thing", "Morphs through"], ["place", "Passes through"], ["feel", "Feels"], ["who", "Performer"]];
const IDEA_EXAMPLES = { thing: ["a nautilus", "a jellyfish"], place: ["a moonlit shore"], feel: ["slow and dreamy"] };
function ideaChip(kind, text, tag) {
  return `<span class="ir ${kind}">${esc(text)}${tag ? ` <i>${esc(tag)}</i>` : ""}</span>`;
}
function ideaRows(rows, extra) {
  return IDEA_ROWS.filter(([kind]) => rows[kind] && rows[kind].length)
    .map(([kind, label]) => `<div class="ir-row"><span class="ir-k ${kind}">${esc(label)}</span>${rows[kind].join("")}${(extra && extra[kind]) || ""}</div>`)
    .join("");
}
function ideaReadingHtml(easy) {
  if (!String(easy.idea || "").trim()) {
    const rows = {};
    Object.entries(IDEA_EXAMPLES).forEach(([kind, words]) => { rows[kind] = words.map((w) => ideaChip(`${kind} example`, w)); });
    return `${ideaRows(rows)}<p class="note ir-foot">Any of these, split by commas. Empty, and the vibe decides.</p>`;
  }
  const have = state.ideaReading && state.ideaReading.key === ideaKey() ? state.ideaReading.data : undefined;
  if (have === undefined) return `<p class="note ir-foot">Reading your line...</p>`;
  if (!have) return "";
  if (have.error) return `<p class="note ir-foot">${esc(have.error)}</p>`;
  const grow = have.grow || {};
  const bare = (x) => String(x).toLowerCase().replace(/^(a|an|the)\s+/, "").trim();  // the grow plan drops the article
  const fresh = new Set([].concat(grow.own || [], grow.nouns || [], grow.scenes || []).map(bare));
  const isNew = (x) => fresh.has(bare(x)) ? "new" : "";
  const rows = { thing: [], place: [], feel: [], who: [] };
  (have.objects || []).forEach((o) => rows.thing.push(ideaChip("thing", o, isNew(o))));
  (have.own || []).forEach((o) => rows.thing.push(ideaChip("thing", o, "new")));
  if (have.theme && rows.thing.length > 6) {  // a theme's fifteen things: six chips and a count, the rest in its title
    const names = [].concat(have.objects || [], have.own || []);
    rows.thing = rows.thing.slice(0, 6).concat(`<span class="ir thing more" title="${esc(names.slice(6).join(", "))}">+${names.length - 6} more</span>`);
  }
  if (have.family) rows.thing.push(ideaChip("thing", String(have.family).replace(/-/g, " "), have.theme ? "joins in" : "fills the rest"));
  (have.scenes || []).forEach((s) => rows.place.push(ideaChip("place", s, isNew(s) || "scene")));
  const extra = {};
  if (have.theme) extra.thing = `<span class="ir-note">the ${esc(have.theme)} theme</span>`;  // idea.THEMES: a theme word grows its things
  if (have.feel) {
    rows.feel.push(ideaChip("feel", (have.feel.words || []).join(", ")));
    const knobs = Object.entries(have.feel.macros || {}).map(([k, v]) => `${k.charAt(0).toUpperCase()}${k.slice(1)} ${Math.round(Number(v) * 100)}`);
    if (have.feel.look) knobs.push(`Look ${lookLabel(have.feel.look)}`);
    if (knobs.length) extra.feel = `<span class="ir-note">${esc(knobs.join(" · "))}</span>`;
  }
  if (have.performer) {
    rows.who.push(ideaChip("who", have.performer.cue || have.performer.style || "performing"));
    extra.who = `<span class="ir-note">${Number(easy.performer || 0) > 0 ? "Polly performs it" : "Polly is off (Work in progress)"}</span>`;
  }
  const body = ideaRows(rows, extra);
  if (!body) return `<p class="note ir-foot">Nothing to morph between yet: name things (a nautilus, a jellyfish), a place or how it feels.</p>`;
  const things = (grow.own || []).length + (grow.nouns || []).length;
  const places = new Set((grow.scenes || []).map(bare)).size;
  const stills = Number(grow.count) || things + (grow.scenes || []).length;
  const parts = [things ? `${things} ${things === 1 ? "thing" : "things"}` : "", places ? `${places} ${places === 1 ? "place" : "places"}` : ""].filter(Boolean);
  const foot = stills ? `<p class="note ir-foot">Make draws ${stills} new ${stills === 1 ? "still" : "stills"} first (${parts.join(", ")}), about ${grow.seconds || 20} s.</p>` : "";
  return body + foot;
}
function ideaReadingLine(easy) {
  if (!state.ideaReading || state.ideaReading.key !== ideaKey()) scheduleIdea();
  const html = ideaReadingHtml(easy);
  return `<div class="idea-reading" id="easy-idea-reading" aria-live="polite"${html ? "" : " hidden"}>${html}</div>`;
}
function paintIdeaReading() {
  const el = document.getElementById("easy-idea-reading");
  if (!el) return;  // another screen: the next render draws it
  const html = ideaReadingHtml(state.easy || {});
  el.innerHTML = html;
  el.hidden = !html;
}
let chainTimer = null;
function chainKey() {
  const e = state.easy || {};
  const m = window.XENO_MACROS ? window.XENO_MACROS() : null;
  const counts = (state.stills && state.stills.counts && state.stills.counts[e.vibe]) || null;
  return JSON.stringify([e.song, state.audioId, e.vibe, e.idea || "", e.scenes || "off", !!e.scenesChosen, e.energyPreset, e.tier, e.aspect, easyLength(e), e.lengthStart,
    e.morphs, e.ownFolder, e.ownId, e.pins || {}, m && m.speed, counts]);
}
function scheduleChain(key) {
  if (chainTimer) clearTimeout(chainTimer);
  chainTimer = setTimeout(() => { chainTimer = null; loadChain(key); }, 350);
}
async function loadChain(key) {
  if (!state.easy || !state.easy.song || !state.easy.vibe) { state.chain = { key, data: null }; return; }
  state.chain = Object.assign({}, state.chain || {}, { key, loading: true });
  let data;
  try {
    const res = await api("/api/simple/chain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()) });
    const body = await res.json().catch(() => ({}));
    data = res.ok ? body : { error: body.detail || "The chain could not be read." };
  } catch (err) {
    data = { error: "The chain could not be read." };
  }
  if (!state.easy || chainKey() !== key) return;  // the choices moved on; a newer request follows
  state.chain = { key, data };
  render();
}
// A vibe's library rows (objects, then scenes, each with its thumbnail), for the Chain row's picker and the lane's swap.
function libraryRows(vibe) {
  if (!vibe) return [];
  state.libraryRows = state.libraryRows || {};
  if (state.libraryRows[vibe]) return state.libraryRows[vibe];
  if (state.stills && state.stills.vibe === vibe && Array.isArray(state.stills.rows)) return state.stills.rows;
  state.libraryLoading = state.libraryLoading || {};
  if (!state.libraryLoading[vibe]) {
    state.libraryLoading[vibe] = true;
    setTimeout(() => loadLibraryRows(vibe), 0);
  }
  return null;
}
async function loadLibraryRows(vibe) {
  try {
    const res = await api(`/api/stills?vibe=${encodeURIComponent(vibe)}`);
    const data = res.ok ? await res.json() : {};
    state.libraryRows[vibe] = Array.isArray(data.rows) ? data.rows : [];
  } catch (err) {
    state.libraryRows[vibe] = [];
  }
  state.libraryLoading[vibe] = false;
  render();
}
function libraryPicker(vibe, act, slot, used) {
  const rows = libraryRows(vibe);
  if (!rows) return `<p class="note">Reading the ${esc(vibe)} library...</p>`;
  if (!rows.length) return `<p class="note">The ${esc(vibe)} library is empty: grow some stills on the Library row first.</p>`;
  const tile = (r) => {
    const taken = used.has(r.file);
    return `<button type="button" class="lib-thumb${taken ? " taken" : ""}${r.kind === "scene" ? " is-scene" : ""}" data-act="${act}" data-slot="${slot}" data-file="${esc(r.file)}"${taken ? " disabled" : ""} title="${esc(r.noun + (r.kind === "scene" ? " (scene)" : "") + (taken ? " · already in the chain" : ""))}"><img src="${esc(media(r.thumb))}" alt="" loading="lazy"><i>${esc(r.noun)}</i></button>`;
  };
  const objects = rows.filter((r) => r.kind !== "scene");
  const scenes = rows.filter((r) => r.kind === "scene");
  return `<div class="lib-picker">
      ${objects.length ? `<div class="lib-group"><span>Objects</span><div class="lib-tiles">${objects.map(tile).join("")}</div></div>` : ""}
      ${scenes.length ? `<div class="lib-group"><span>Scenes</span><div class="lib-tiles">${scenes.map(tile).join("")}</div></div>` : ""}
    </div>`;
}
function chainRow(easy) {
  if (!easy.vibe) return "";
  const key = chainKey();
  if (!state.chain || state.chain.key !== key) scheduleChain(key);
  const have = state.chain && state.chain.data;
  const stale = !!(state.chain && state.chain.key !== key);
  const pins = easy.pins || {};
  const nPins = Object.keys(pins).length;
  let strip = "";
  let facts = "";
  if (!easy.song) strip = `<p class="note">Choose a song and the chain appears here.</p>`;
  else if (!have) strip = `<p class="note">Reading the chain...</p>`;
  else if (have.error) strip = `<p class="note">${esc(have.error)}</p>`;
  else {
    const slots = (have.stills || []).map((s) => {
      const title = `${s.index + 1}. ${s.noun}${s.kind === "scene" ? " (scene)" : ""}${s.user ? " (your image)" : ""}${s.pinned ? " · pinned, click × to let the pick choose" : " · click to choose another"}`;
      return `<div class="chain-slot${s.pinned ? " pinned" : ""}${s.kind === "scene" ? " is-scene" : ""}${easy.chainPick === s.index ? " picking" : ""}">
          <button type="button" class="chain-pick" data-act="easy-chain-slot" data-slot="${s.index}" title="${esc(title)}" aria-label="${esc(title)}">${s.thumb ? `<img src="${esc(media(s.thumb))}" alt="" loading="lazy">` : `<span class="chain-user">yours</span>`}<i>${esc(s.noun)}</i></button>
          ${s.pinned ? `<button type="button" class="unpin" data-act="easy-unpin" data-slot="${s.index}" title="Unpin: let the pick choose this slot" aria-label="Unpin slot ${s.index + 1}">×</button>` : ""}
        </div>`;
    }).join("");
    strip = `<div class="chain-strip${stale ? " stale" : ""}" role="list" aria-label="The chain">${slots}</div>`;
    facts = `${have.count} stills, ${have.morphs} morph${have.morphs === 1 ? "" : "s"}${have.long_song ? ", one a shot" : ""}${have.length_s ? ` on the ${have.length_s} s cut` : ""}${have.scene_mode && have.scene_mode !== "off" ? ` · scenes ${have.scene_mode}` : ""}${have.pinned && have.pinned.length ? ` · ${have.pinned.length} pinned` : ""}${have.dropped_pins && have.dropped_pins.length ? ` · ${have.dropped_pins.length} pin${have.dropped_pins.length === 1 ? "" : "s"} past the chain or gone from the library` : ""}`;
  }
  let picker = "";
  if (have && !have.error && easy.chainPick != null && (have.stills || []).some((s) => s.index === easy.chainPick)) {
    const slot = have.stills.find((s) => s.index === easy.chainPick);
    const used = new Set(have.stills.filter((s) => s.index !== slot.index).map((s) => s.file));
    picker = `<div class="chain-picker">
        <p class="note">Slot ${slot.index + 1} is <b>${esc(slot.noun)}</b>${slot.kind === "scene" ? " (a scene)" : ""}. Pick what goes there instead; it holds through Make.
          <button type="button" class="text" data-act="easy-chain-cancel">Cancel</button></p>
        ${libraryPicker(easy.vibe, "easy-pin", slot.index, used)}
      </div>`;
  }
  return `<div class="simple-seg own-row chain-row"><span>Chain</span>
      <div class="chain-body">
        <div class="chain-head"><span class="note">${esc(facts || "The stills this Make morphs through, in order")}</span>${nPins ? `<button type="button" class="text" data-act="easy-chain-reset" title="Let the pick choose every slot again">Unpin all</button>` : ""}</div>
        ${strip}
        ${picker}
      </div>
    </div>
    <p class="note">The stills this Make will morph through, in order, the way the draft previews them. Click a slot to choose another object or scene from the library: a pinned slot holds through Make, the rest are picked fresh each time (the idea line, Scenes and Length move them). After the cut, the shots lane under the player swaps one object and re-renders only the two morphs that touch it.</p>`;
}

// The foreshadow layer: the next object arrives before its shot, the way a new sound is introduced before it takes
// the song. Trace (its edges glowing in the vibe's tint), Negative (its luma-flipped ghost), Slices (strips of it
// interleaving and multiplying) or Silhouette (its shape filled with the tint); the amount rides the "other" stem
// under the Intensity knob, starts a bar or so early (Speed), and across a hard cut the object that just left
// echoes out for a beat. Auto picks by the vibe: trace on a dark vibe, slices on a bright one.
const FORESHADOW_NOTES = {
  auto: "The vibe's own mode: a trace on a dark vibe, slices on a bright one.",
  off: "No foreshadowing: each morph lands on its own.",
  trace: "The next object's edges glow in before it arrives, in the vibe's tint.",
  negative: "The next object's negative ghosts in over the picture.",
  slices: "Strips of the next object interleave and multiply toward the cut; Chaos sets how many and how jittery.",
  silhouette: "The next object's shape fills in with the vibe's tint, edges traced.",
};
function foreshadowRow(easy) {
  const current = easy.foreshadow || "auto";
  const choices = [["auto", "Auto"], ["off", "Off"], ["trace", "Trace"], ["negative", "Negative"], ["slices", "Slices"], ["silhouette", "Silhouette"]];
  return `${simpleSeg("easy-foreshadow", current, choices, "Foreshadow")}
      <p class="note">${esc(FORESHADOW_NOTES[current] || FORESHADOW_NOTES.auto)} It rides the song's other stem under Intensity, starts earlier with Speed, and echoes a beat after a cut into Polly or your own clip.</p>`;
}

// Scenes: a second kind of still beside the objects (wide frames in the vibe's light, grown with "Grow 8 scenes" on the
// Library row). Off morphs objects alone; Mix lands a scene on every passage change (the song's section switches, else
// every fourth still) and morphs scenes into objects and back; Only morphs scenes alone. The make body carries it as
// scene_stills; the record says which stills were scenes and a re-cut keeps them.
const SCENES_NOTES = {
  off: "Objects only: every morph travels between single objects.",
  mix: "A scene at every passage change, objects between: the shore morphs into the orb, the orb into the corridor of mirrors.",
  only: "Scenes alone: every morph travels between wide frames in the vibe's light.",
};
function scenesRow(easy) {
  const chosen = ["off", "mix", "only"].includes(easy.scenes) ? easy.scenes : "off";
  // a line that names a place turns Off into Mix unless Off was picked by hand (idea.shape_state): the row shows what
  // the cut does, not the untouched default (the cut's screen said Off over a cut full of scenes, 27 Oct)
  const reading = ideaReading();
  const fromLine = chosen === "off" && !easy.scenesChosen && !!(reading && reading.scenes && reading.scenes.length);
  const current = fromLine ? "mix" : chosen;
  const have = ((state.stills || {}).counts || {})[easy.vibe] || {};
  const none = current !== "off" && easy.vibe && state.stills && !Number(have.scenes || 0)
    ? ` This vibe has no scenes yet: grow some on the Library row first, or the cut stays objects only.` : "";
  const why = fromLine ? " Your line names a place, so its scenes are mixed in; pick Off to keep objects only." : "";
  return `${simpleSeg("easy-scenes", current, [["off", "Off"], ["mix", "Mix"], ["only", "Only"]], "Scenes")}
      <p class="note">${esc((SCENES_NOTES[current] || SCENES_NOTES.off) + why + none)}</p>`;
}

function machineRows(easy) {
  const hw = (state.simpleOptions && state.simpleOptions.hardware) || {};
  const detected = hw.detected || {};
  const autoLabel = "Auto";
  const tiers = [["auto", autoLabel]].concat((hw.tiers || [{id: "cpu", label: "CPU"}, {id: "8gb", label: "8 GB"}, {id: "12gb", label: "12 GB"}, {id: "24gb", label: "24 GB+"}]).map((t) => [t.id, t.label]));
  const endpoint = (state && state.endpoint) || "http://127.0.0.1:8188";
  const ok = state && state.comfyOk;
  return `${simpleSeg("easy-gpu", easy.gpuTier || "auto", tiers, "GPU")}
      <div class="simple-seg machine-where"><span>Renders on</span>
        <div class="toggle" role="group" aria-label="Renders on">
          <label class="ghost cloud-toggle">ComfyUI at <input type="text" id="easy-endpoint" value="${esc(endpoint)}" spellcheck="false" aria-label="ComfyUI address"></label>
          <span class="note">${detected.label ? esc(detected.label) + " · " : ""}${ok ? "connected" : "not answering: Make will play the vibe's pictures in the browser, no render"} · open weights on this machine</span>
        </div>
      </div>`;
}

function simpleOptions(easy) {
  const energy = easy.energyPreset || "dense";
  const aspect = easy.aspect || "9:16";
  // Cloud Final morphs object cuts only (cloud_final has no clips path): a clips cut leaves the chip out and renders here
  const clips = morphSource(easy) === "clips";
  if (clips && easy.tier === "cloud") easy.tier = "draft";
  const tier = easy.tier || "draft";
  const tiers = [["draft", "Draft"], ["fast", "Fast Final"], ["final", "Final"], ["cloud", "Cloud Final"]].filter((t) => !(clips && t[0] === "cloud"));
  const orbit = easy.stemOrbit !== false;
  const fx = easy.fx !== false;
  const card = !!easy.endCard;
  const vertical = tier === "final" ? (easy.vertical === "crop" ? "crop" : "native") : "crop";
  const cloudInfo = (state.simpleOptions && state.simpleOptions.cloud_final) || {};
  const vertNote = aspect !== "9:16" ? (aspect === "16:9" ? "" : " Each shot is reframed around the object as it changes.")
    : vertical === "native" ? " Native vertical: rendered in portrait (448×768), upscaled to 1080×1920, the object centred whole."
    : tier === "final" ? " Each shot is cropped from the 16:9 render around the object as it changes."
    : tier === "cloud" ? ` Portrait: rendered at ${cloudInfo.render || "576x1024"} on Comfy Cloud, scaled to 1080×1920 here, the object centred whole.`
    : tier === "fast" ? " Portrait: the Draft's portrait morphs (320×576), each upscaled to 1080×1920."
    : " Portrait Draft: every still re-laid whole on black, the morphs rendered in portrait (320×576) and composed at 540×960, so wide objects are never clipped.";
  return `<div class="simple-opts" data-tour="easy-options">
      ${simpleSeg("easy-energy", energy, [["flow", "Flow"], ["dense", "Dense"]], "Energy")}
      ${simpleSeg("easy-aspect", aspect, [["16:9", "16:9"], ["9:16", "9:16"], ["1:1", "1:1"]], "Aspect")}
      ${simpleSeg("easy-length", String(easyLength(easy)), [["0", "Full song"], ["60", "60 s"], ["30", "30 s"], ["15", "15 s"]], "Length")}
      <p class="note">${esc(lengthNote(easy))}</p>
      ${simpleSeg("easy-tier", tier, tiers, "Model")}
      ${clips ? `<p class="note">Cloud Final morphs object cuts only; a clips cut renders here.</p>` : ""}
      ${tier === "cloud" ? cloudFinalRow(easy) : ""}
      ${machineRows(easy)}
      ${aspect === "9:16" && tier === "final" ? simpleSeg("easy-vertical", vertical, [["native", "Native"], ["crop", "Crop"]], "Vertical") : ""}
      ${morphControl(easy, tier, aspect, vertical)}
      ${simpleSeg("easy-fx", fx ? "on" : "off", [["on", "On"], ["off", "Off"]], "Beat FX")}
      ${simpleSeg("easy-orbit", orbit ? "on" : "off", [["on", "On"], ["off", "Off"]], "Subject orbit")}
      ${simpleSeg("easy-card", card ? "on" : "off", [["off", "Off"], ["on", "On"]], "End card")}
      <p class="note">${esc(energy === "dense" ? "Dense: a song cuts two bars a shot and a bar on the drop, light punches on the downbeats, and loops a chain of up to 30 morphs so every handoff stays one continuous transformation; a clip under 20 s cuts a shot a bar, then every half bar from the drop, with stutters, holds and punches." : "Flow: one morph per section, cut on the bar.")}
      ${esc(vertNote)}
      ${esc(tier === "final" ? " " + finalEtaText() : tier === "fast" ? " Fast Final: the Draft's morphs (LTX 0.9.5), each upscaled 4x to 1080×1920 and cut at full size. The motion is the Draft's, the picture is full size, in a fraction of the Final's time."
        : tier === "cloud" ? ` Cloud Final: ${cloudInfo.model || "LTX"} on Comfy Cloud, scaled to full size here.` : " Draft: LTX 0.9.5, the quick pass.")}
      ${esc(easy.overlay ? "" : " Clean export: no waveform or text on the picture.")}</p>
    </div>`;
}

// Morph count: Auto (from clip length + BPM) or a fixed number of forms, with a time/VRAM estimate.
const MORPH_COST = {draft: {s: 35, vram_gb: 7.5}, fast: {s: 55, vram_gb: 7.5}, final: {s: 230, vram_gb: 11.2}, final_916: {s: 270, vram_gb: 11.4},
  cloud: {s: 45, vram_gb: 2}};  // Final: 340 s a morph measured 28 Oct, less the encoder read once a prompt and the quarter-size upscale; cloud: three at once on Comfy Cloud, then the upscale here (dense.COST serves the live figure)
function autoMorphs(energy) {
  const m = state.simpleOptions && state.simpleOptions.morphs;
  if (m && m.auto) return m.auto;
  const secs = easySongSeconds() || 20;
  const bar = 4 * 60 / (Number(state.tempo) || 120);
  return Math.max(1, Math.round(secs / (energy === "dense" ? bar / 2 : Math.max(bar * 2, 4))));
}
// Where a render's time goes on this machine (12 GB RTX 3080 Ti, 32 GB RAM): measured 28 Oct from ComfyUI's log of a
// 1:33:59 Final (15 morphs, 20 s, 9:16: 5,469 s of morphs, 152 s of cut) and the upscale benchmarks. The tooltip on the
// estimate under Forms (Tys: "find out what parts of that took the longest so we can have that in a tool tip").
const TIME_PARTS = {
  draft: ["Draft: each morph about 20 s on LTX 0.9.5 (the first loads the model, about 45 s more).",
    "The cut: about 60 s for 20 s at 540×960."],
  fast: ["Fast Final: each morph about 40 s, the Draft's 20 s and about 20 s to upscale it to 1080×1920.",
    "The cut: about 2½ minutes for 20 s at 1080×1920."],
  final: ["Final: each morph about 4½ min (measured on LTX-2.3, whose 24 GB of weights do not fit the 12 GB card and are read again every step):",
    "• reading the prompt: 1 min, once for each different prompt (shots that share one go back to back)",
    "• drawing it, 8 steps at 224×384: 2¼ min",
    "• refining it, 3 steps at 448×768: 1 min",
    "• the 4x upscale to 1080×1920: ½ min",
    "The first morph loads the models: about 5 min more.",
    "The cut: about 2½ minutes for 20 s at 1080×1920."],
  cloud: ["Cloud Final: each morph about 60 s on Comfy Cloud, three at once, then a few seconds to scale it to full size here.",
    "The cut: about 2½ minutes for 20 s at 1080×1920."],
};
function timeTip(tier) {
  return (TIME_PARTS[tier] || TIME_PARTS.draft).join("\n");
}
function morphEstimate(count, tier, aspect, vertical) {
  const key = tier === "final" && aspect === "9:16" && vertical === "native" ? "final_916" : (["final", "fast", "cloud"].includes(tier) ? tier : "draft");
  // the desk's own figures are measured on this card; Cloud Final's comes from the server (dense.COST, cloud_final)
  const served = (((state.simpleOptions || {}).morphs || {}).cost || {})[key];
  const c = key === "cloud" && served && Number(served.s) > 0 ? served : MORPH_COST[key];
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
      <span class="note time-tip" title="${esc(timeTip(tier))}">${esc(`${n} form${n === 1 ? "" : "s"}: ${morphEstimate(n, tier, aspect, vertical)}`)} ⓘ</span>
      <span class="note guard-live">${auto ? "" : esc(morphGuardText(n, tier))}</span>
    </div>`;
}
// Live guardrail hint, mirroring configs/guardrails.json morph_density (15 sweet spot, 18 hard per 20 s).
function morphGuardText(n, tier) {
  const secs = easySongSeconds() || 20;
  const cap = Math.max(1, Math.round(secs / 20 * 15));
  const hard = Math.max(cap, Math.round(secs / 20 * 18));
  const expert = localStorage.getItem("xeno-guard-expert") === "1";
  // Cloud Final's own cap (cloud_final.MAX_MORPHS): its credits, not the density guardrail
  const cloudMax = Number(((state.simpleOptions || {}).cloud_final || {}).max_morphs) || 16;
  if (tier === "cloud" && n > cloudMax) return `Cloud Final renders at most ${cloudMax} morphs a cut`;
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
  // a row with no song and no vibe is a Director dry run or a test animatic (1.5 s renders named by their id): not a video of yours
  const rows = (state.videos || []).filter((row) => row.song || row.vibe).slice(0, 12);
  if (!rows.length) {
    return `<section class="panel span gallery" id="my-videos"><h3>My videos</h3><p class="note">Every video you make shows up here, with its recipe code.</p></section>`;
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
      length: String(easyLength(easy)),
      performer: String(easy.performer || 0),
      // the loaded song itself: the server plans the window the Make will trim with the Make's own planner (its
      // sections, its drop, the guardrail's budget), so the count and the clock shown are the cut's
      audio_id: state.audioId || "",
      vibe: easy.vibe || "",
      speed: String(((window.XENO_MACROS ? window.XENO_MACROS() : null) || {}).speed ?? 0.5),
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

// The Timeline panel (docs/TIMELINE.md): the finished cut under the player as tracks (GET /api/videos/<id>/shots,
// lane.build). Each block is a shot, its width the shot's share of the cut, its colour the section; between the shots sit
// the boundary handles; under them the song's passages. Polly's, your own and the generated runs sit as bars over the
// shots. A click on a shot or a boundary seeks the player there and opens its drawer: Play (Morph / Hold), Look and FX
// intensity for a shot, Handoff (Morph / Cut) and the dressing (a transition or a boundary kind) for a boundary. Apply
// re-cuts from the cached morphs with these edits (POST /api/jobs/<id>/recut with shot_overrides / boundary_overrides,
// no GPU) and the record keeps them. The GPU buttons (swap, re-render, generate here) post their own routes.
const SECTION_HUES = { intro: 210, calm: 200, sustain: 190, build: 40, release: 60, drop: 350, drop_late: 20, outro: 230 };
function timelineState(easy, lane) {
  // the edits as the desk holds them before Apply, seeded from what the record persisted; a new cut starts afresh
  if (!easy.tl || easy.tl.id !== lane.id) {
    easy.tl = { id: lane.id, shots: JSON.parse(JSON.stringify(lane.shot_overrides || {})), bounds: JSON.parse(JSON.stringify(lane.boundary_overrides || {})) };
  }
  return easy.tl;
}
function canonOverride(o) {
  const out = {};
  Object.keys(o || {}).sort().forEach((k) => {
    const v = o[k];
    if (v == null || v === "" || v === "auto" || v === "morph") return;
    out[k] = typeof v === "number" ? Math.round(v * 1000) / 1000 : (v && typeof v === "object" && !Array.isArray(v)) ? canonOverride(v) : v;
  });
  return out;
}
function timelineDirty(easy, lane) {
  const tl = timelineState(easy, lane);
  let n = 0;
  [["shots", "shot_overrides"], ["bounds", "boundary_overrides"]].forEach(([mine, theirs]) => {
    const keys = new Set(Object.keys(tl[mine] || {}).concat(Object.keys(lane[theirs] || {})));
    keys.forEach((k) => {
      if (JSON.stringify(canonOverride(tl[mine][k])) !== JSON.stringify(canonOverride((lane[theirs] || {})[k]))) n += 1;
    });
  });
  return n;
}
function setShotOverride(easy, lane, index, key, value) {
  if (!lane) return;
  const tl = timelineState(easy, lane);
  const k = String(index);
  const o = Object.assign({}, tl.shots[k] || {});
  if (value == null || value === "" || value === "auto" || value === "morph") delete o[key];
  else o[key] = value;
  if (Object.keys(o).length) tl.shots[k] = o;
  else delete tl.shots[k];
}
function setBoundOverride(easy, lane, index, fx) {
  setBoundKey(easy, lane, index, "fx", !fx || fx === "auto" ? null : fx);
}
function setBoundKey(easy, lane, index, key, value) {
  if (!lane) return;
  const tl = timelineState(easy, lane);
  const k = String(index);
  const o = Object.assign({}, tl.bounds[k] || {});
  if (value == null || value === 0) delete o[key];
  else o[key] = value;
  if (Object.keys(o).length) tl.bounds[k] = o;
  else delete tl.bounds[k];
}
// The order edits (Tys, 28 Oct: "trim and move cuts", "reorder, delete, duplicate"), all for Apply, no GPU
// (dense.arrange_shots): a slot plays another shot's morph (source), a shot goes (drop), a cut moves (shift).
function sourceOf(tl, index) {
  const o = tl.shots[String(index)] || {};
  return o.source != null ? Number(o.source) : index;
}
function setSource(easy, lane, index, src) {
  setShotOverride(easy, lane, index, "source", src === index ? null : src);
}
function beatPeriod(lane) {
  const b = (lane && lane.beats) || [];
  if (b.length > 2) {
    const gaps = b.slice(1).map((t, i) => t - b[i]).filter((g) => g > 0).sort((x, y) => x - y);
    if (gaps.length) return gaps[Math.floor(gaps.length / 2)];
  }
  return 60 / (Number(state.tempo) || 120);
}
function shotOrderRow(lane, tl, s) {
  const n = lane.shots.length;
  const o = tl.shots[String(s.index)] || {};
  const src = sourceOf(tl, s.index);
  const moved = src !== s.index ? `plays shot ${src + 1}'s morph` : "";
  return `<div class="simple-seg tl-order"><span>Order</span><div class="toggle chips" role="group" aria-label="Order">
      <button type="button" class="chip" data-act="easy-tl-move" data-index="${s.index}" data-value="-1"${s.index < 1 ? " disabled" : ""}>◀ Move left</button>
      <button type="button" class="chip" data-act="easy-tl-move" data-index="${s.index}" data-value="1"${s.index >= n - 1 ? " disabled" : ""}>Move right ▶</button>
      <button type="button" class="chip" data-act="easy-tl-dup" data-index="${s.index}"${s.index >= n - 1 ? " disabled" : ""}>Duplicate into the next</button>
      <button type="button" class="chip${o.drop ? " on" : ""}" data-act="easy-tl-drop" data-index="${s.index}" aria-pressed="${o.drop ? "true" : "false"}">${o.drop ? "Deleted · restore" : "Delete"}</button>
      ${src !== s.index ? `<button type="button" class="chip" data-act="easy-tl-source-clear" data-index="${s.index}">Its own morph</button>` : ""}</div></div>
    ${o.drop ? `<p class="note">Deleted: the shot before plays on through its time.</p>` : moved ? `<p class="note">This slot ${esc(moved)}.</p>` : ""}`;
}
function cutShiftRow(lane, tl, s) {
  const o = tl.bounds[String(s.index)] || {};
  const shift = Number(o.shift || 0);
  const beat = beatPeriod(lane);
  const step = (k) => Math.round((shift + k * beat) * 1000) / 1000;
  return `<div class="simple-seg tl-shift"><span>Move it</span><div class="toggle chips" role="group" aria-label="Move this cut">
      <button type="button" class="chip" data-act="easy-tl-shift" data-index="${s.index}" data-value="${step(-1)}">◀ a beat earlier</button>
      <button type="button" class="chip" data-act="easy-tl-shift" data-index="${s.index}" data-value="${step(-0.5)}">◀ half</button>
      <button type="button" class="chip" data-act="easy-tl-shift" data-index="${s.index}" data-value="${step(0.5)}">half ▶</button>
      <button type="button" class="chip" data-act="easy-tl-shift" data-index="${s.index}" data-value="${step(1)}">a beat later ▶</button>
      ${shift ? `<button type="button" class="chip" data-act="easy-tl-shift" data-index="${s.index}" data-value="0">Back</button>` : ""}</div></div>
    ${shift ? `<p class="note">Moved ${shift > 0 ? "later" : "earlier"} by ${Math.abs(shift).toFixed(2)} s (${(Math.abs(shift) / beat).toFixed(1)} beats).</p>` : ""}`;
}
function kindLabel(lane, id) {
  const rows = (lane.choices && lane.choices.transition_kinds) || [];
  const row = rows.find((r) => r.id === id);
  return row ? row.label : id;
}
function shotsLane(easy) {
  const id = easyVideoId();
  if (!id || easy.showcase || easy.playedHere) return "";
  const lane = state.lane && state.lane.id === id ? state.lane : null;
  if (!lane) {
    if (!state.laneLoading || state.laneLoading !== id) {
      state.laneLoading = id;
      setTimeout(() => loadLane(id), 0);
    }
    return `<div class="shots-lane" aria-label="Timeline"><p class="note">Reading the cut's shots...</p></div>`;
  }
  if (!lane.shots || !lane.shots.length) return lane.note ? `<p class="note">${esc(lane.note)}</p>` : "";
  const total = Math.max(Number(lane.duration) || 0, 0.001);
  // Swap an object: in swap mode a click on a shot picks the still it lands on, and the library picker under the lane
  // replaces it (POST /api/jobs/<id>/swap: only the two morphs that touch that still are rendered again, the rest kept)
  const canSwap = lane.swappable !== false && Array.isArray(lane.stills) && lane.stills.length > 0;
  const swapping = canSwap && !!easy.swapMode;
  const tl = timelineState(easy, lane);
  const picked = easy.tlPick && easy.tlFor === id ? easy.tlPick : null;
  const blocks = lane.shots.map((s) => {
    const w = (100 * (Number(s.seconds) || 0)) / total;
    const hue = SECTION_HUES[s.section] != null ? SECTION_HUES[s.section] : 260;
    const o = tl.shots[String(s.index)] || {};
    const held = o.play === "hold";
    const edited = held || !!o.look || o.fx_intensity != null || !!o.timing || !!o.grade || Array.isArray(o.effects) || o.source != null || !!o.drop;
    const label = s.to ? `${s.from} → ${s.to}` : s.from;
    const marks = `${s.style && s.style !== "melt" ? ` · ${morphStyleLabel(s.style)}` : ""}${o.timing ? ` · ${MORPH_TIMING_LABELS[o.timing] || o.timing}` : ""}${s.pinned ? " · pinned" : ""}${s.swapped ? " · swapped" : ""}${held ? " · held" : ""}${o.look ? ` · look ${o.look}` : ""}${o.fx_intensity != null ? ` · FX ${o.fx_intensity}` : ""}${o.grade ? " · colour" : ""}${Array.isArray(o.effects) ? ` · effects ${o.effects.length ? o.effects.join("+") : "none"}` : ""}${s.rerendered ? " · re-rendered" : ""}${s.generated != null ? " · generated" : ""}${s.dream != null ? " · dream" : ""}${s.performer ? " · Polly" : ""}${s.own ? " · your clip" : ""}`;
    const title = `Shot ${s.index + 1} · ${clockText(s.start)} · ${s.seconds} s${s.section ? ` · ${s.section}` : ""}${s.transition ? ` · ${s.transition}` : ""}${label ? ` · ${label}` : ""}${marks}`;
    const pick = swapping && s.still != null;
    const act = pick ? `data-act="easy-swap-pick" data-slot="${s.still}" data-at="${s.start}"` : `data-act="easy-tl-shot" data-index="${s.index}" data-at="${s.start}"`;
    const cls = `shot${s.boundary ? " boundary" : ""}${s.transition ? " has-transition" : ""}${s.pinned ? " pinned" : ""}${s.swapped ? " swapped" : ""}${pick ? " swap" : ""}${pick && easy.swapSlot === s.still ? " picked" : ""}${held ? " held" : ""}${edited ? " edited" : ""}${s.rerendered ? " rerendered" : ""}${s.generated != null ? " generated" : ""}${!swapping && picked && picked.kind === "shot" && picked.index === s.index ? " picked" : ""}`;
    const badge = s.style && s.style !== "melt" ? `<b class="tl-style">${esc(morphStyleLabel(s.style))}</b>` : "";  // how this morph changes
    // each tile shows the cut itself at the shot's middle (GET /api/videos/<id>/frame.jpg), so a shot is a picture, not a word
    const mid = Number(s.start) + Number(s.seconds) / 2;
    const thumb = `--thumb:url('${media(`/api/videos/${encodeURIComponent(id)}/frame.jpg?t=${mid.toFixed(2)}&w=160&v=${lane.version || 0}`)}')`;
    if (s.dropped || o.drop) {  // deleted: a sliver at its place, the drawer restores it
      return `<button type="button" class="${cls} dropped" style="flex:0 0 7px;--hue:${hue}" data-act="easy-tl-shot" data-index="${s.index}" data-at="${s.start}" title="${esc(`Shot ${s.index + 1} deleted · click to restore`)}" aria-label="${esc(`Shot ${s.index + 1} deleted`)}"></button>`;
    }
    return `<button type="button" class="${cls}" style="width:${w.toFixed(3)}%;--hue:${hue};${thumb}" ${act} title="${esc(title)}" aria-label="${esc(title)}"><b class="tl-n">${s.index + 1}</b>${badge}<i>${esc(s.to || s.from || "")}</i></button>`;
  }).join("");
  // the boundaries: one handle at each join (into shot i, i from 1): Morph or Cut, and what dresses it (the pickers'
  // choice on Auto, else the transition or boundary kind set by hand)
  const bounds = lane.shots.filter((s) => s.index > 0).map((s) => {
    const left = (100 * Number(s.start)) / total;
    const o = tl.bounds[String(s.index)] || {};
    const prevHeld = (tl.shots[String(s.index - 1)] || {}).play === "hold";
    const cut = prevHeld || s.handoff === "cut";
    const dress = o.fx && o.fx !== "auto" ? o.fx : "";
    const kindNow = dress === "none" ? "" : dress ? kindLabel(lane, dress) : (s.transition || "");
    const what = `${cut ? "Cut" : "Morph"}${kindNow ? ` · ${kindNow}` : ""}`;
    const glyph = kindNow ? "◆" : cut ? "┃" : "·";
    const shifted = Number(o.shift || 0) ? " moved" : "";
    const cls = `join${cut ? " cut" : ""}${kindNow ? " dressed" : ""}${dress || prevHeld || shifted ? " edited" : ""}${picked && picked.index === s.index && easy.tlTab === "join" ? " picked" : ""}`;
    const title = `The join into shot ${s.index + 1} · ${clockText(s.start)} · ${what}${s.boundary ? ` · ${s.boundary}` : ""} · click to change it`;
    return `<button type="button" class="${cls}" style="left:${left.toFixed(3)}%" data-act="easy-tl-bound" data-index="${s.index}" data-at="${s.start}" title="${esc(title)}" aria-label="${esc(title)}"><span>${glyph === "·" ? "" : glyph}</span></button>`;
  }).join("");
  const overlays = (lane.overlays || []).map((o) => {
    const left = (100 * Number(o.start)) / total;
    const w = (100 * (Number(o.end) - Number(o.start))) / total;
    const title = o.kind === "performer" ? `Polly: ${o.label}` : o.kind === "generated" ? `Generated run: ${o.label}` : `Your clip: ${o.label}`;
    return `<span class="overlay ${esc(o.kind)}" style="left:${left.toFixed(3)}%;width:${w.toFixed(3)}%" title="${esc(title)}">${esc(o.kind === "performer" ? `Polly · ${o.label}` : o.label)}</span>`;
  }).join("");
  // the song under the shots: its passages (a click seeks there) and the drop
  const passages = (lane.sections || []).map((sec) => {
    const left = (100 * Number(sec.start)) / total;
    const w = (100 * (Number(sec.end) - Number(sec.start))) / total;
    const hue = SECTION_HUES[sec.section] != null ? SECTION_HUES[sec.section] : 260;
    return `<button type="button" class="passage" style="left:${left.toFixed(3)}%;width:${w.toFixed(3)}%;--hue:${hue}" data-act="easy-seek" data-at="${sec.start}" title="${esc(`${sec.section} · ${clockText(sec.start)} to ${clockText(sec.end)}`)}"><i>${esc(sec.section)}</i></button>`;
  }).join("");
  const dropMark = lane.drop != null && Number(lane.drop) > 0 ? `<span class="drop-mark" style="left:${((100 * Number(lane.drop)) / total).toFixed(3)}%" title="${esc(`the drop · ${clockText(lane.drop)}`)}"></span>` : "";
  const song = passages || dropMark ? `<div class="lane-song" aria-label="Song">${passages}${dropMark}</div>` : "";
  const facts = [`${lane.shots.length} shots`, lane.morphs ? `${lane.morphs} morphs over ${lane.objects} objects` : "", lane.pace ? `${lane.pace} pace` : "",
    (lane.sections || []).length > 1 ? `${lane.sections.length} passages` : "", lane.swaps ? `${lane.swaps} swap${lane.swaps === 1 ? "" : "s"}` : "",
    lane.rerenders ? `${lane.rerenders} re-render${lane.rerenders === 1 ? "" : "s"}` : "", lane.inserts ? `${lane.inserts} generated run${lane.inserts === 1 ? "" : "s"}` : "", lane.dreams ? `${lane.dreams} dream${lane.dreams === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ");
  const hint = swapping ? "click a shot to swap the object it lands on" : "click a shot, or the seam between two, to change it";
  const toggle = swapping ? `<button type="button" class="text lane-swap-toggle" data-act="easy-swap-mode" aria-pressed="true">Done swapping</button>` : "";
  let picker = "";
  if (swapping && easy.swapSlot != null) {
    const slot = lane.stills.find((x) => x.index === easy.swapSlot);
    if (slot) {
      const used = new Set(lane.stills.map((x) => x.file));
      const shot = lane.shots.find((x) => x.still === slot.index);
      const opens = slot.index === 0;  // the chain's first still: no shot lands on it, the cut opens on it
      const ends = slot.index === lane.stills.length - 1;
      const verb = opens ? "opens on" : "lands on";
      const touched = opens || ends ? "the one morph that touches it is" : "the two morphs that touch it are";
      picker = `<div class="lane-swap">
          <p class="note">${opens ? "The cut" : shot ? `Shot ${shot.index + 1}` : "The cut"} ${verb} <b>${esc(slot.noun)}</b>${slot.kind === "scene" ? " (a scene)" : ""}${slot.swapped ? ", swapped in earlier" : ""}. Pick what it ${verb} instead: ${touched} rendered again on the GPU and the cut re-composed (a morph's worth of the render time above each, plus the re-cut), the rest of the cut stays as it is.
            <button type="button" class="text" data-act="easy-swap-cancel">Cancel</button></p>
          ${libraryPicker(lane.vibe || easy.resultVibe || easy.vibe, "easy-swap", slot.index, used)}
        </div>`;
    }
  }
  // the opening tile: the chain's first still, which no shot lands on (every shot names the still it lands on), so
  // the cut's opening picture can be swapped too; outside swap mode it seeks to the top
  let opening = "";
  const first = lane.opens_on || (Array.isArray(lane.stills) ? lane.stills[0] : null);
  if (first) {
    const pick = swapping;
    const act = pick ? `data-act="easy-swap-pick" data-slot="0" data-at="0"` : `data-act="easy-seek" data-at="0"`;
    const title = `Opens on ${first.noun}${first.kind === "scene" ? " (scene)" : ""}${first.pinned ? " · pinned" : ""}${first.swapped ? " · swapped" : ""}${pick ? " · click to swap it" : ""}`;
    const cls = `shot open${first.pinned ? " pinned" : ""}${first.swapped ? " swapped" : ""}${pick ? " swap" : ""}${pick && easy.swapSlot === 0 ? " picked" : ""}`;
    opening = `<div class="lane-open"><button type="button" class="${cls}" ${act} title="${esc(title)}" aria-label="${esc(title)}"><i>opens on ${esc(first.noun)}</i></button></div>`;
  }
  const pending = timelineDirty(easy, lane);
  const anyEdits = Object.keys(tl.shots).length + Object.keys(tl.bounds).length + Object.keys(lane.shot_overrides || {}).length + Object.keys(lane.boundary_overrides || {}).length;
  const applyRow = lane.editable !== false && !swapping
    ? `<div class="lane-apply-row">
        ${anyEdits ? `<button type="button" class="text" data-act="easy-tl-reset">Reset the timeline</button>` : ""}
        <span class="note">${pending ? `${pending} edit${pending === 1 ? "" : "s"} waiting for Apply (the bar at the bottom).` : "Edits wait for Apply in the bar at the bottom, and stay with the cut."}</span>
      </div>`
    : "";
  const drawer = swapping ? "" : timelineDrawer(easy, lane, tl, picked);
  return `<div class="shots-lane tl-panel${swapping ? " swapping" : ""}" aria-label="Timeline">
      <div class="lane-head"><span>Timeline</span><span class="note">${esc(facts)} · ${hint}</span>${toggle}</div>
      <div class="lane-track" id="lane-track" data-total="${total}">
        <div class="lane-overlays">${overlays}</div>
        ${opening}
        <div class="lane-shots-wrap"><div class="lane-shots">${blocks}</div><div class="lane-joins">${bounds}</div></div>
        ${song}
        <span class="lane-playhead" id="lane-playhead" aria-hidden="true"></span>
      </div>
      ${picker}
      ${drawer}
      ${applyRow}
    </div>`;
}

// A shot's own colour (Tys, 28 Oct: "there should be some options you can play with effects, colours"): five sliders,
// each 0 where it does nothing, written to the shot's override as {grade: {...}} (dense.shot_overrides_of, effects.grade).
const GRADE_ROWS = [["hue", "Hue", -180, 180, 5, "°"], ["saturation", "Saturation", -1, 1, 0.05, ""], ["brightness", "Brightness", -1, 1, 0.05, ""],
  ["contrast", "Contrast", -1, 1, 0.05, ""], ["warmth", "Warmth", -1, 1, 0.05, ""]];
function shotColourRows(o, index) {
  const g = o.grade || {};
  const rows = GRADE_ROWS.map(([key, label, lo, hi, step, unit]) => {
    const v = Number(g[key] || 0);
    return `<label class="tl-grade"><span>${label}</span><input type="range" class="tl-grade-in" min="${lo}" max="${hi}" step="${step}" value="${v}" data-index="${index}" data-key="${key}" aria-label="${label} for this shot" /><b>${v ? `${v > 0 ? "+" : ""}${key === "hue" ? Math.round(v) : v.toFixed(2)}${unit}` : "0"}</b></label>`;
  }).join("");
  const any = Object.keys(g).length;
  return `<div class="tl-colour"><div class="tl-colour-head"><span>Colour</span>${any ? `<button type="button" class="text" data-act="easy-tl-grade-clear" data-index="${index}">As shot</button>` : `<span class="note">as shot</span>`}</div>${rows}</div>`;
}
// A shot's own effects: As the cut, or its own set of the four (none is a set too).
function shotEffectsRow(o, index) {
  const own = Array.isArray(o.effects);
  const on = new Set(own ? o.effects : []);
  const chips = EFFECTS.filter((id) => id !== "smear").map((id) => `<button type="button" class="chip${own && on.has(id) ? " on" : ""}" data-act="easy-tl-effect" data-index="${index}" data-value="${id}" aria-pressed="${own && on.has(id) ? "true" : "false"}">${esc(EFFECT_LABELS[id] || id)}</button>`).join("");
  return `<div class="simple-seg tl-effects"><span>Effects</span><div class="toggle chips" role="group" aria-label="Effects on this shot">
      <button type="button" class="chip${own ? "" : " on"}" data-act="easy-tl-effect" data-index="${index}" data-value="cut" aria-pressed="${own ? "false" : "true"}">As the cut</button>${chips}</div></div>`;
}

// The drawer under the timeline: one shot, in four tabs (Tys, 28 Oct: "the time line is a bit confusing to use").
// Shot: how it plays and where it sits; Look: its look, colour, effects and FX; Join: the seam into it (Morph or Cut,
// moved a beat, dressed with a transition); Regenerate: what the GPU can redo (object cuts). A seam opens Join.
const TL_TABS = [["shot", "Shot"], ["look", "Look"], ["join", "Join"], ["gpu", "Regenerate"]];
const TL_TAB_NOTES = {
  shot: "How this shot plays and where it sits. The beat timing never moves.",
  look: "This shot's own look, colour and effects. Leave them as the cut and the knobs decide.",
  join: "The seam into this shot: a morph that flows or a cut that jumps, moved a beat, dressed with a transition.",
  gpu: "These render again on the GPU (Draft): about a morph's time each, then the re-cut.",
};
function timelineDrawer(easy, lane, tl, picked) {
  if (!picked) return "";
  const s = lane.shots.find((x) => x.index === picked.index);
  if (!s) return "";
  const n = lane.shots.length;
  const choices = lane.choices || {};
  const o = tl.shots[String(s.index)] || {};
  const bo = tl.bounds[String(s.index)] || {};
  const held = o.play === "hold";
  const prevHeld = (tl.shots[String(s.index - 1)] || {}).play === "hold";
  const label = s.to ? `${s.from} → ${s.to}` : s.from;
  const under = s.performer ? "Polly's shot" : s.own ? "your clip" : s.generated != null ? "a generated run" : "";
  const canGpu = lane.rerenderable !== false && s.still != null && !under;
  const dream = dreamRow(lane, s, choices);
  const tabs = TL_TABS.filter(([id]) => (id !== "join" || s.index > 0) && (id !== "gpu" || canGpu || dream));
  const tab = tabs.some(([id]) => id === easy.tlTab) ? easy.tlTab : "look";
  const edited = {
    shot: held || o.source != null || !!o.drop || !!o.timing,
    look: !!o.look || !!o.grade || Array.isArray(o.effects) || o.fx_intensity != null,
    join: !!bo.fx || !!bo.shift || prevHeld,
    gpu: false,
  };
  const head = `<div class="tl-drawer-head">
      <button type="button" class="text tl-step" data-act="easy-tl-step" data-value="-1"${s.index < 1 ? " disabled" : ""} aria-label="The shot before">◀</button>
      <b>Shot ${s.index + 1} <small>of ${n}</small></b>
      <button type="button" class="text tl-step" data-act="easy-tl-step" data-value="1"${s.index >= n - 1 ? " disabled" : ""} aria-label="The shot after">▶</button>
      <span class="note">${esc(clockText(s.start))} · ${esc(String(s.seconds))} s${label ? ` · ${esc(label)}` : ""}${under ? ` · ${esc(under)}` : ""}</span>
      <button type="button" class="text" data-act="easy-tl-close">Close</button></div>
    <div class="tl-tabs" role="tablist">${tabs.map(([id, name]) => `<button type="button" role="tab" class="tl-tab${id === tab ? " on" : ""}" data-act="easy-tl-tab" data-value="${id}" aria-selected="${id === tab ? "true" : "false"}">${name}${edited[id] ? '<i class="tl-dot" aria-label="edited"></i>' : ""}</button>`).join("")}</div>
    <p class="note tl-tab-note">${esc(TL_TAB_NOTES[tab])}</p>`;
  let body = "";
  if (tab === "shot") {
    body = `<div class="simple-seg"><span>Play</span><div class="toggle chips" role="group" aria-label="Play">
        <button type="button" class="chip${held ? "" : " on"}" data-act="easy-tl-play" data-index="${s.index}" data-value="morph" aria-pressed="${held ? "false" : "true"}">${s.own ? "Play" : "Morph"}</button>
        <button type="button" class="chip${held ? " on" : ""}" data-act="easy-tl-play" data-index="${s.index}" data-value="hold" aria-pressed="${held ? "true" : "false"}">Hold</button></div></div>
      ${shotOrderRow(lane, tl, s)}
      ${under || held ? "" : timingRow(o.timing || "auto", "easy-tl-timing", s.index, lane.morph_timing || "smooth")}`;
  } else if (tab === "look") {
    const fxVal = o.fx_intensity != null ? Number(o.fx_intensity) : null;
    body = `${lookRow(o.look || "auto", "easy-tl-look", s.index)}
      ${shotColourRows(o, s.index)}
      ${shotEffectsRow(o, s.index)}
      <div class="simple-seg tl-fx-row"><span>Beat FX</span><input id="tl-fx" type="range" min="0" max="1" step="0.05" value="${fxVal != null ? fxVal : 0.8}" data-index="${s.index}" aria-label="Beat FX intensity for this shot" /><b id="tl-fx-readout">${fxVal != null ? fxVal.toFixed(2) : "as the knob"}</b>${fxVal != null ? `<button type="button" class="text" data-act="easy-tl-fx-clear" data-index="${s.index}">As the knob</button>` : ""}</div>`;
  } else if (tab === "join") {
    const prev = lane.shots.find((x) => x.index === s.index - 1) || {};
    const hardAnyway = s.handoff === "cut" && !prev.hold && !prevHeld;  // a clip arrives or leaves here: a cut whatever is set
    const fx = bo.fx || "auto";
    const rows = choices.transition_kinds || [];
    const groups = [["premium", "Premium transitions"], ["core", "Core"], ["classic", "Classic"], ["boundary", "Boundary kinds"]];
    const options = `<option value="auto"${fx === "auto" ? " selected" : ""}>Auto${s.transition ? ` (now ${esc(s.transition)})` : " (the pickers decide)"}</option>`
      + `<option value="none"${fx === "none" ? " selected" : ""}>None</option>`
      + groups.map(([g, name]) => {
        const rs = rows.filter((r) => r.group === g);
        return rs.length ? `<optgroup label="${name}">${rs.map((r) => `<option value="${esc(r.id)}"${fx === r.id ? " selected" : ""}>${esc(r.label)}</option>`).join("")}</optgroup>` : "";
      }).join("");
    body = `<div class="simple-seg"><span>Handoff</span><div class="toggle chips" role="group" aria-label="Handoff">
        <button type="button" class="chip${prevHeld ? "" : " on"}" data-act="easy-tl-handoff" data-index="${s.index}" data-value="morph" aria-pressed="${prevHeld ? "false" : "true"}"${hardAnyway ? " disabled" : ""}>Flow</button>
        <button type="button" class="chip${prevHeld ? " on" : ""}" data-act="easy-tl-handoff" data-index="${s.index}" data-value="cut" aria-pressed="${prevHeld ? "true" : "false"}"${hardAnyway ? " disabled" : ""}>Cut</button></div></div>
      ${hardAnyway ? `<p class="note">A clip arrives or leaves here: this seam is a cut whatever is set.</p>` : ""}
      ${cutShiftRow(lane, tl, s)}
      <div class="simple-seg tl-dress-row"><span>Transition</span><select id="tl-dress" data-index="${s.index}" aria-label="Transition at this seam">${options}</select></div>`;
  } else {
    const insertS = choices.insert_seconds || [5, 10, 15];
    const renderS = choices.render_s || [2, 5];
    const lengthOpts = [];
    for (let v = renderS[0]; v <= renderS[1]; v += 1) lengthOpts.push(v);
    const variants = choices.rerender_variants || ["auto"];
    const variantName = (v) => (v === "auto" ? "by the stills" : v === "object" ? "object to object" : v === "scene" ? "scene to scene" : v.replace("-", " to "));
    body = `${canGpu ? `${morphStyleRow(s.style || "melt", "easy-tl-style", s.index, false)}
      <div class="tl-gpu-row"><button type="button" class="ghost" data-act="easy-tl-swap" data-slot="${s.still}">Swap the object it lands on</button></div>
      <div class="tl-gpu-row"><button type="button" class="ghost" data-act="easy-tl-rerender" data-index="${s.index}">Re-render this morph</button>
        <label>seed <input id="tl-seed" type="number" placeholder="next" min="0" step="1" aria-label="Seed, empty for the next one" /></label>
        <label>length <select id="tl-render-s" aria-label="Seconds of source"><option value="">as it is</option>${lengthOpts.map((v) => `<option value="${v}">${v} s</option>`).join("")}</select></label>
        <label>prompt <select id="tl-variant" aria-label="Prompt variant">${variants.map((v) => `<option value="${esc(v)}">${esc(variantName(v))}</option>`).join("")}</select></label></div>
      <div class="tl-gpu-row"><button type="button" class="ghost" data-act="easy-tl-insert" data-index="${s.index}">Generate here</button>
        <label>length <select id="tl-insert-s" aria-label="Seconds to generate">${insertS.map((v) => `<option value="${v}"${v === 10 ? " selected" : ""}>${v} s</option>`).join("")}</select></label></div>` : ""}
      ${dream}`;
  }
  return `<div class="tl-drawer" id="tl-drawer">${head}<div class="tl-tab-body">${body}</div></div>`;
}

// Dream this span (xenoform.dream): Z-Image Turbo img2img over 1 to 3 s from this shot, every other frame (12 a second),
// cut in like a generated run; on any cut, Draft or Final, over morphs, a generated run or an earlier dream.
function dreamRow(lane, s, choices) {
  if (lane.editable === false || s.performer || s.own) return "";
  const lengths = choices.dream_seconds || [1, 2, 3];
  const perFrame = Number(choices.dream_s_per_frame) || 2.6;
  const est = (n) => clockText(46 + perFrame * n * 12);
  return `<div class="tl-gpu tl-dream">
        <div class="tl-gpu-row"><button type="button" class="ghost" data-act="easy-tl-dream" data-index="${s.index}">Dream here</button>
          <label>length <select id="tl-dream-s" aria-label="Seconds to dream">${lengths.map((v) => `<option value="${v}"${v === 2 ? " selected" : ""}>${v} s · about ${esc(est(v))}</option>`).join("")}</select></label>
          <label>depth <select id="tl-dream-depth" aria-label="How far the dream strays"><option value="light">light</option><option value="deep">deep</option></select></label></div>
        <p class="note">${s.dream != null ? "This shot is dreamed already; dreaming again dreams over the dream. " : ""}Z-Image Turbo re-dreams every other frame of this shot and the next ones (12 a second, each held and blended into the next): the object keeps its place while its surface and its meaning drift, StreamDiffusion style. About ${esc(String(perFrame))} s of GPU a frame, cut in like a generated run.</p>
      </div>`;
}
async function dreamRun(index) {
  const id = easyVideoId();
  const lane = state.lane && state.lane.id === id ? state.lane : null;
  if (!id || !lane) return;
  const lenEl = document.getElementById("tl-dream-s");
  const depthEl = document.getElementById("tl-dream-depth");
  const seconds = Number((lenEl && lenEl.value) || 2);
  const depth = (depthEl && depthEl.value) || "light";
  const shot = lane.shots.find((x) => x.index === Number(index)) || {};
  await postCutEdit(id, "dream", { first: Number(index), seconds, depth }, `Dreaming ${seconds} s from shot ${Number(index) + 1} on the GPU (${depth})`, shot.start);
}

// A timeline edit that goes through the job (the re-cut with the overrides, a re-render, a generated run): the making
// screen shows it, the lane reloads when it lands and the player seeks to what was clicked.
async function postCutEdit(id, route, body, detail, at, stage) {
  if (!id || !state.easy) return false;
  try {
    const res = await api(`/api/jobs/${encodeURIComponent(id)}/${route}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      state.easy.note = err.detail || "That did not start.";
      render();
      return false;
    }
    state.job = Object.assign({}, state.job || {}, { id, status: "running", stage: stage || "restyle", progress: 0.05, detail });
    state.easy.tlSeek = at != null ? Number(at) : null;
    setEasyPhase("making");
    state.easy.recutting = true;
    render();
    poll(id);
    return true;
  } catch (err) {
    state.easy.note = "That did not start.";
    render();
    return false;
  }
}
async function applyTimeline() {
  const id = easyVideoId();
  const lane = state.lane && state.lane.id === id ? state.lane : null;
  if (!id || !lane || !state.easy) return;
  const tl = timelineState(state.easy, lane);
  const pick = state.easy.tlPick;
  const at = pick ? (lane.shots.find((x) => x.index === pick.index) || {}).start : null;
  const n = timelineDirty(state.easy, lane);
  await postCutEdit(id, "recut", { shot_overrides: tl.shots, boundary_overrides: tl.bounds },
    `Re-cutting from the cached morphs with ${n} timeline edit${n === 1 ? "" : "s"}`, at, "assemble");
}
// Re-render one shot's morph: the seed, length and prompt fields of the drawer, and ``style`` when a Morph chip asked
// for another way the object changes (the shot keeps its own style otherwise).
async function rerenderShot(index, style) {
  const id = easyVideoId();
  const lane = state.lane && state.lane.id === id ? state.lane : null;
  if (!id || !lane) return;
  const seedEl = document.getElementById("tl-seed");
  const lenEl = document.getElementById("tl-render-s");
  const varEl = document.getElementById("tl-variant");
  const body = { shot: Number(index), variant: (varEl && varEl.value) || "auto" };
  if (seedEl && seedEl.value !== "") body.seed = Number(seedEl.value);
  if (lenEl && lenEl.value !== "") body.render_s = Number(lenEl.value);
  if (style && MORPH_STYLES.includes(style)) body.style = style;
  const shot = lane.shots.find((x) => x.index === Number(index)) || {};
  const how = body.style ? ` as ${morphStyleLabel(body.style)}` : "";
  await postCutEdit(id, "rerender", body, `Re-rendering shot ${Number(index) + 1}'s morph${how} on the GPU`, shot.start);
}
async function insertRun(index) {
  const id = easyVideoId();
  const lane = state.lane && state.lane.id === id ? state.lane : null;
  if (!id || !lane) return;
  const lenEl = document.getElementById("tl-insert-s");
  const seconds = Number((lenEl && lenEl.value) || 10);
  const shot = lane.shots.find((x) => x.index === Number(index)) || {};
  await postCutEdit(id, "insert", { first: Number(index), seconds, pins: (state.easy && state.easy.pins) || {} },
    `Generating ${seconds} s of new morphs from shot ${Number(index) + 1} on the GPU`, shot.start);
}

// Swap one still of the finished cut (the lane's picker): the desk re-renders the two morphs that touch it on the GPU
// and re-composes; the job runs like a re-cut, the making screen shows it, the lane reloads when it is done.
async function swapStill(id, slot, file) {
  if (!id || !state.easy || slot == null || !file) return;
  try {
    const res = await api(`/api/jobs/${encodeURIComponent(id)}/swap`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: Number(slot), file }) });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      state.easy.note = err.detail || "The swap did not start.";
      render();
      return;
    }
    state.job = Object.assign({}, state.job || {}, { id, status: "running", stage: "restyle", progress: 0.05, detail: "Re-rendering the two morphs that touch the swapped still" });
    state.easy.swapSlot = null;
    state.easy.swapMode = false;
    setEasyPhase("making");
    state.easy.recutting = true;
    render();
    poll(id);
  } catch (err) {
    state.easy.note = "The swap did not start.";
    render();
  }
}

async function loadLane(id) {
  try {
    const res = await api(`/api/videos/${encodeURIComponent(id)}/shots`);
    const data = res.ok ? await res.json() : { id, shots: [], note: "The cut's shots could not be read." };
    state.lane = Object.assign({ id }, data);
  } catch (err) {
    state.lane = { id, shots: [], note: "The cut's shots could not be read." };
  }
  if (state.laneLoading === id) state.laneLoading = "";
  if (state.easy) {
    state.easy.tl = null;  // the edits start again from what the record now holds
    if (state.easy.tlFor !== id) { state.easy.tlPick = null; state.easy.tlFor = id; }
  }
  render();
  const seek = state.easy ? state.easy.tlSeek : null;
  if (seek != null) {  // after an edit the player comes back where you were working
    state.easy.tlSeek = null;
    const player = document.getElementById("player");
    if (player) {
      const go = () => { try { player.currentTime = Math.max(0, Number(seek) || 0); } catch (e) { /* not seekable yet */ } };
      if (player.readyState >= 1) go();
      else player.addEventListener("loadedmetadata", go, { once: true });
    }
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
  easy.cloudFinalOk = false;  // a recipe that says Cloud Final still needs the credits tick
  easy.vertical = recipe.vertical_mode || "";
  easy.morphs = recipe.morph_count || "auto";
  easy.fx = recipe.beat_fx !== false;
  easy.overlay = !!recipe.beat_overlay;
  easy.endCard = !!recipe.end_card;
  easy.danceFx = recipe.dance_fx || "auto";
  easy.foreshadow = recipe.foreshadow || "auto";
  easy.morphStyle = recipe.morph_style || "auto";
  easy.morphTiming = recipe.morph_timing || "smooth";
  easy.effects = Array.isArray(recipe.effects) ? recipe.effects.filter((x) => EFFECTS.includes(x)) : [];
  easy.scenes = ["off", "mix", "only"].includes(recipe.scene_stills) ? recipe.scene_stills : "off";
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

// Edit in Resolve: the cut laid out as an editor's timeline (a clip a shot, the song, markers) and zipped with its media.
// The pack is also left unzipped beside the cut, so on this machine the timeline file can be imported from there.
async function easyEdit() {
  const id = easyVideoId();
  if (!id) return;
  state.easy.editBusy = true;
  render();
  try {
    const res = await api(`/api/videos/${id}/edit`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || "The edit pack did not build.");
    state.easy.editUrl = body.url;
    state.easy.editTimeline = body.timeline;
    state.easy.editInfo = `${body.shots} shots on V1, ${body.song ? "the song on A1, " : ""}${body.markers} marker${body.markers === 1 ? "" : "s"}, ${body.mb} MB. `
      + `Premiere: File › Import, the same file; Final Cut: ${body.fcpxml}. Unzipped in ${body.folder}`;
    state.easy.editOpened = await easyEditOpen(id);
  } catch (err) {
    state.easy.note = String(err.message || err);
  }
  state.easy.editBusy = false;
  render();
}

// The pack's folder in Explorer with the timeline file selected (POST /api/videos/{id}/edit/reveal); false where the
// desk cannot open a window on this screen.
async function easyEditOpen(id) {
  try {
    const res = await api(`/api/videos/${encodeURIComponent(id || easyVideoId())}/edit/reveal`, { method: "POST" });
    const body = await res.json();
    return !!(res.ok && body.opened);
  } catch (err) {
    return false;
  }
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
  const pad = (n) => String(n).padStart(2, "0");
  // two hours is 2:00:32, not 120:32 (the 12 s demo's Final, 27 Oct)
  return s >= 3600 ? `${Math.floor(s / 3600)}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}` : `${Math.floor(s / 60)}:${pad(s % 60)}`;
}

function easySongSeconds() {
  const ends = (state.scenes || []).map((scene) => Number(scene.end || 0)).filter((t) => t > 0);
  return ends.length ? Math.max.apply(null, ends) : Number(state.duration || 20) || 20;
}

// The prototype stage: until a Length is picked by hand, a song longer than PROTO_MAX_S is made as a PROTO_S Draft
// around the drop (a few minutes, not twenty), and the cut's screen then offers the whole song and Final. A song under
// it is short enough to make whole. A Length chip clicked once is kept (lengthS, saved with the other choices).
const PROTO_S = 30;
const PROTO_MAX_S = 45;
function easyLength(easy) {
  const e = easy || (state && state.easy) || {};
  if (e.lengthS != null && e.lengthS !== "") return Number(e.lengthS) || 0;
  return easySongSeconds() > PROTO_MAX_S ? PROTO_S : 0;
}
function easyLengthIsProto(easy) {
  const e = easy || (state && state.easy) || {};
  return (e.lengthS == null || e.lengthS === "") && easyLength(e) > 0;
}

// The plan's own estimate (/api/simple/options, shown as "About N min" before Make) seeds the clock;
// the constant below it was tuned for a 20 s clip and pinned every long run at 95 %.
function easyPlanEta() {
  const plan = state && state.simpleOptions && state.simpleOptions.plan;
  const seconds = plan && plan.estimate && Number(plan.estimate.seconds);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
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
  const hit = /morph (\d+) of (\d+)/i.exec(String(job.detail || ""));
  if (!hit) return Number(easy.eta || EASY_ETA_GPU_S);
  const done = Number(hit[1]);
  const total = Number(hit[2]);
  const now = (Date.now() - easy.startedAt) / 1000;
  if (!easy.firstMorph || done < easy.firstMorph.done) easy.firstMorph = { done, at: now };
  const span = done - easy.firstMorph.done;
  // until two morphs have reported, the pace is the plan's own GPU seconds per morph (a Final morph is minutes, not 4.5 s)
  const plan = state.simpleOptions && state.simpleOptions.plan && state.simpleOptions.plan.estimate;
  const planned = plan && Number(plan.gpu_seconds) > 0 ? Number(plan.gpu_seconds) / Math.max(1, total) : 4.5;
  const pace = span > 0 ? (now - easy.firstMorph.at) / span : planned;
  const tail = plan && Number(plan.look_seconds) > 0 ? Number(plan.look_seconds) : 2;
  return now + (total - done) * pace + tail;
}

// What the server is doing, in a word, from the job's stage and detail.
function easyStageWord(job) {
  const stage = String((job && job.stage) || "");
  const detail = String((job && job.detail) || "").toLowerCase();
  if (detail.startsWith("saving") || detail.startsWith("burning")) return "finishing";
  if (stage === "qa") return "checking";
  if (stage === "assemble" && /cutting shot|house look|cutting to the beat/.test(detail)) return "cutting to the beat";
  if (stage === "restyle") return /performer/.test(detail) ? "Polly" : /your clip/.test(detail) ? "your clips" : "morphs";
  if (stage === "analyze" || stage === "animatic") return "reading the song";
  return stage || "starting";
}

// "1:24 elapsed · morphs · about 3:10 left". The first number is always elapsed; the remaining time is the
// server's when it sends one (job.eta_s), else the plan estimate re-paced on the morphs; never "almost there"
// outside the last stages.
function easyEtaText() {
  const easy = state && state.easy;
  if (!easy || !easy.startedAt) return "About half a minute";
  const job = state.job || {};
  const elapsed = (Date.now() - easy.startedAt) / 1000;
  const draft = job.video ? "Draft playing · " : "";
  const word = easyStageWord(job);
  const served = job.eta_s === null || job.eta_s === undefined ? NaN : Number(job.eta_s);
  // the server re-estimates on each stage tick; between ticks the page counts the seconds since that tick down
  // itself, so "about 2:40 left" does not sit still for half a minute while the first morph renders
  const sinceTick = easy.jobAt ? (Date.now() - easy.jobAt) / 1000 : 0;
  const left = Number.isFinite(served) ? served - sinceTick : easyEtaLive() - elapsed;
  if (word === "checking" || word === "finishing" || !(left > 0)) return `${draft}${clockText(elapsed)} elapsed · ${word}`;
  return `${draft}${clockText(elapsed)} elapsed · ${word} · about ${clockText(Math.max(10, left))} left`;
}

// "· morphs 2:10 · Polly 17:48 · cut 0:52 · check 0:14" from the job's per-phase seconds, when the server sent them.
function tookBreakdown(breakdown) {
  if (!breakdown || typeof breakdown !== "object") return "";
  const names = [["morphs", "morphs"], ["performer", "Polly"], ["cut", "cut"], ["qa", "check"]];
  const parts = names.filter(([key]) => Number(breakdown[key]) >= 1).map(([key, label]) => `${label} ${clockText(breakdown[key])}`);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
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
  const len = easyLength(easy || state.easy);
  return len && secs > len ? len : secs;
}
function lengthNote(easy) {
  const secs = easySongSeconds();
  const len = easyLength(easy);
  if (easyLengthIsProto(easy)) return `The prototype: ${len} s around the drop, quick to make. The whole song (${clockText(secs)}) is one press on the cut's screen, or pick Full song here.`;
  if (!len) return `The whole song (${clockText(secs)}). Shorter cuts are centred on the drop.`;
  return secs > len ? `${len} s around the drop, starting on a beat with short fades.` : `The song is already under ${len} s, so the whole song.`;
}
function easyPlanFacts(easy) {
  const plan = state.simpleOptions && state.simpleOptions.plan;
  const secs = easySongSeconds();
  const len = easyLength(easy);
  const dense = (easy.energyPreset || "dense") === "dense";
  const song = easyVideoSeconds(easy) > 20;  // dense.LONG_SONG_S: the story plan (viscous pace) from 20 s, the clip plan under it
  const rows = [["Video", `${clockText(easyVideoSeconds(easy))}${len && secs > len ? " around the drop" : " (the whole song)"}`]];
  if (plan && plan.shots) {
    rows.push(["Shots", plan.reuse ? `${plan.shots} on the beat, over a loop of ${plan.morphs} morphs` : `${plan.shots} morphs on the beat`]);
  } else {
    rows.push(["Shots", dense ? (song ? "Two bars a shot, a bar on the drop" : "A shot a bar, a half bar after the drop") : "One per section"]);
  }
  rows.push(["Cut", dense ? (song ? "Every two bars, every bar on the drop" : "Every bar, every half bar on the drop") : "On the bar"]);
  if (plan && plan.performer) rows.push(["Performer", `${plan.performer} shots of Polly (MiniMax H3)`]);
  rows.push(["Time", easyTimeFact()]);
  return rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
}
function easyTimeFact() {
  if (state.comfyOk === false) return "No render: ComfyUI is not answering, so Make plays the vibe's pictures in the browser";
  const plan = state.simpleOptions && state.simpleOptions.plan;
  if (plan && plan.estimate && plan.estimate.seconds) {
    const e = plan.estimate;
    if ((state.easy && state.easy.tier) === "cloud") {
      return `About ${clockText(e.seconds)} (${clockText(e.gpu_seconds || 0)} of morphs on Comfy Cloud, ${clockText(e.look_seconds || 0)} look here)`;
    }
    return `About ${clockText(e.seconds)} on this GPU (${clockText(e.gpu_seconds || 0)} morphs, ${clockText(e.look_seconds || 0)} look)`;
  }
  const guess = easyEtaGuess();
  return `About ${clockText(guess)}${state.easy && state.easy.warm ? "" : " (first run)"}`;
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
    const job = state.job || {};
    const elapsed = (Date.now() - state.easy.startedAt) / 1000;
    // the server's weighted progress when it sends one (job.overall); else elapsed against the plan's estimate, never pinned at 95 %
    const overall = Number(job.overall);
    const frac = Number.isFinite(overall) && overall > 0 ? overall : Math.min(0.9, elapsed / Math.max(1, easyEtaLive()));
    bar.style.width = `${Math.round(Math.max(0.02, Math.min(1, frac)) * 100)}%`;
    tabTitle(`(${Math.round(Math.max(0.02, Math.min(1, frac)) * 100)}%) Making · Xenoform`);
  }
}

// Step away while it renders (a Final is twenty minutes): the tab title counts up, and when the cut is ready the tab
// says so and, if the page is hidden and notifications are allowed (asked once, on the first Make), a notification
// does too. The title comes back when you return to the tab.
const TAB_TITLE = document.title;
function tabTitle(text) {
  document.title = text || TAB_TITLE;
}
function askToNotify() {
  try {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
  } catch (err) {}
}
function notifyReady(job, failed) {
  const easy = (state && state.easy) || {};
  const vibe = vibeById(easy.resultVibe || easy.vibe);
  const what = `${vibe ? vibe.name : "Your video"}${easy.songLabel ? ` · ${easy.songLabel}` : ""}`;
  tabTitle(failed ? "Render stopped · Xenoform" : "✓ Your video is ready · Xenoform");
  try {
    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      const took = Number(job && (job.took_s || job.seconds)) || 0;
      new Notification(failed ? "The render stopped" : "Your video is ready", {
        body: failed ? `${what}: open the desk to see why.` : `${what}${took ? ` · took ${clockText(took)}` : ""}`,
        icon: media("/static/vibes/" + ((vibe && vibe.id) || "cosmic") + ".jpg"),
        tag: "xenoform-render",
      });
    }
  } catch (err) {}
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && state && state.easy && state.easy.phase !== "making") tabTitle();
});

// The beat overlay (the waveform and the beat marks drawn on the picture): a labelled row like the rest of Fine-tune,
// not an orphan "Beat overlay · off" button under the drawer.
function beatOverlayRow(easy) {
  const overlay = !!easy.overlay;
  return `<div class="cloud-opts">${simpleSeg("easy-overlay-set", overlay ? "on" : "off", [["off", "Off"], ["on", "On"]], "Beat overlay")}
      <p class="note">${overlay ? "The waveform and the beat marks are drawn on the picture." : "Off: a clean export, nothing drawn on the picture."}</p></div>`;
}

// Paid cloud (Work in progress): the opt-in, then Cloud quality and its cut plan once it is on.
function cloudRows(easy) {
  const paidBox = document.getElementById("paid-cloud");
  const paidLocked = !!(paidBox && paidBox.disabled);
  const optIn = `<label class="addon easy-paid"><input type="checkbox" data-act="easy-paid-cloud" ${state.paidCloud ? "checked" : ""}${paidLocked ? " disabled" : ""}> Paid cloud renders (LTX-2.5 partner node, Comfy Cloud account): off by default, not open weights${paidLocked ? " · locked off by XENO_PAID_CLOUD" : ""}</label>`;
  if (!state.paidCloud) return `<div class="cloud-opts">${optIn}</div>`;
  const cloud = !!easy.cloud;
  return `<div class="cloud-opts">
      ${optIn}
      <button type="button" class="ghost cloud-toggle${cloud ? " on" : ""}" data-act="easy-cloud" aria-pressed="${cloud ? "true" : "false"}">Cloud quality · ${cloud ? "on" : "off"}</button>
      ${cloud ? `<label class="ghost cloud-toggle">Cut plan · ${easy.cutPlan ? `${(easy.cutPlan.shots || []).length} shots` : "auto (~5s on the beat)"}<input type="file" accept="application/json,.json" data-act="easy-cut-plan" hidden></label>${easy.cutPlan ? `<button type="button" class="ghost" data-act="easy-cut-clear">Clear cut plan</button>` : ""}` : ""}
      <p class="note">Cloud quality renders the morphs with LTX-2.5 through a paid Comfy partner node, which is not open weights. You see the price and confirm it first. Off, everything stays on open weights on this machine.</p>
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
  state.easy.knobsTouched = {};
  const body = {
    macros: window.XENO_MACROS ? window.XENO_MACROS() : null,
    dance_fx: state.easy.danceFx || "auto",
    foreshadow: state.easy.foreshadow || "auto",
    stem_orbit: state.easy.stemOrbit !== false,
    beat_fx: state.easy.fx !== false,
    end_card: !!state.easy.endCard,
    morph_timing: state.easy.morphTiming || "smooth",
    effects: state.easy.effects || [],
  };
  if (state.easy.tl && state.easy.tl.id === id) {  // the timeline's edits waiting for Apply ride along with the knobs
    body.shot_overrides = state.easy.tl.shots;
    body.boundary_overrides = state.easy.tl.bounds;
  }
  try {
    // the body went out as the fetch options once, so the desk sent a GET and got a 405 (26 Oct)
    const res = await api(`/api/jobs/${encodeURIComponent(id)}/recut`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      state.easy.note = err.detail || "The re-cut did not start.";
      render();
      return;
    }
    state.job = Object.assign({}, state.job || {}, {id, status: "running", stage: "assemble", progress: 0.05, detail: "Re-cutting from the cached morphs"});
    setEasyPhase("making");
    state.easy.recutting = true;
    render();
    poll(id);
  } catch (err) {
    state.easy.note = "The re-cut did not start.";
    render();
  }
}

// Cloud Final: the same open-weights morphs (LTX-2.5) rendered on Comfy Cloud, three at a time, then scaled to full size
// here (cloud_final). It spends the account's Comfy Cloud credits, so a Make sends it only with this tick.
function cloudFinalRow(easy) {
  const info = (state.simpleOptions && state.simpleOptions.cloud_final) || null;
  if (!info) return `<p class="note">Cloud Final: checking whether this desk can reach Comfy Cloud.</p>`;
  if (!info.ready) return `<p class="note cloud-final-note">${esc(info.why || "Cloud Final is not available on this desk.")}</p>`;
  const est = info.estimate || {};
  const about = est.seconds ? `, about ${clockText(Number(est.seconds))}` : "";
  return `<label class="addon cloud-final-ok"><input type="checkbox" data-act="easy-cloud-final-ok"${easy.cloudFinalOk ? " checked" : ""}>
      Spend my Comfy Cloud credits: ${esc(String(est.morphs || "the"))} ${esc(info.model || "LTX")} morphs on Comfy Cloud, three at a time${esc(about)}.</label>
    <p class="note">Open weights on Comfy's GPUs (${esc(info.model || "LTX")}, ${esc(info.render || "576x1024")}), scaled to full size here. At most ${esc(String(info.max_morphs || 16))} morphs a cut; a morph that fails on Cloud falls back to its Draft.</p>`;
}

async function easyMake() {
  const vibe = vibeById(state.easy.vibe);
  if (!vibe) return;
  if (morphSource(state.easy) === "clips" && state.easy.tier === "cloud") state.easy.tier = "draft";  // Cloud Final has no clips path
  const cf = state.simpleOptions && state.simpleOptions.cloud_final;
  if ((state.easy.tier || "draft") === "cloud" && cf && !cf.ready) {
    // no key on this desk: there is no box to tick, so say why instead
    state.easy.note = cf.why || "Cloud Final is not available on this desk.";
    render();
    return;
  }
  if ((state.easy.tier || "draft") === "cloud" && !state.easy.cloudFinalOk) {
    state.easy.note = state.easy.phase === "result"
      ? "Cloud Final spends your Comfy Cloud credits: go Back to the song, tick the box under Model in Fine-tune, then render."
      : "Cloud Final spends your Comfy Cloud credits: tick the box under Model to run it.";
    render();
    return;
  }
  if (morphSource(state.easy) === "clips" && !state.easy.ownFolder && !state.easy.ownId) {
    state.easy.note = "Your clips first: choose a folder of clips, or drop them on the Your clips row.";
    render();
    return;
  }
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
  state.easy.editUrl = "";
  state.easy.recipe = "";
  state.easy.resultVibe = state.easy.vibe;  // the vibe this cut is made with: the result's title, and "Try another vibe" compares to it
  // what this Make is, for the Render row on the cut's screen: a part of the song (a prototype) offers the whole song,
  // a Draft offers Final
  state.easy.madeLength = easyLength(state.easy);
  state.easy.madeTier = state.easy.tier || "draft";
  state.easy.failed = false;
  state.easy.startedAt = Date.now();
  state.easy.firstMorph = null;
  state.easy.eta = state.comfyOk === false ? EASY_ETA_BROWSER_S : easyPlanEta() || easyEtaGuess();
  if (easyTimer) clearInterval(easyTimer);
  easyTimer = setInterval(tickEasy, 1000);
  setEasyPhase("making");
  askToNotify();  // a Make is the user's click: the one moment a browser lets a page ask
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
  await refreshComfy();
  // (the storyboard's "logic" check no longer blocks a Make: it judged the Director storyboard, which this cut never renders)
  if (!state.comfyOk) {
    state.quality = "live";
    setEasyPhase("result");
    state.easy.playedHere = true;
    state.easy.note = `ComfyUI is not answering at ${(state && state.endpoint) || "http://127.0.0.1:8188"}, so this is the vibe's pictures played in the browser, not a render. Start ComfyUI (Xenoform.bat starts the proxy), then press Make again.`;
    render();
    return;
  }
  if (!state || !state.easy || state.easy.phase !== "making") return;
  state.quality = "turbo";
  state.live = true;
  state.easy.playedHere = false;
  state.easy.note = "Cutting a preview, then the GPU pass.";
  const line = document.getElementById("easy-progress");
  if (line) line.textContent = state.easy.note;
  await generate();
  if (state && state.easy) state.easy.cloudFinalOk = false;  // one tick, one Cloud Final: the next Make asks again
  loadVideos().then(() => {
    const id = easyVideoId();
    const row = (state.videos || []).find((item) => item.id === id);
    if (row && state.easy) state.easy.recipe = row.recipe || "";
  });
  if (state.easy && state.easy.phase === "making" && state.job && state.job.status === "error") {
    state.quality = "live";
    setEasyPhase("result");
    state.easy.playedHere = true;
    state.easy.note = "Playing the pictures for this vibe.";
    render();
  }
}

function placeKey(node) {
  if (!node || node === document.body || node === document.documentElement) return "";
  if (node.id) return `#${node.id}`;
  if (!node.dataset || !node.dataset.act) return "";
  return ["act", node.dataset.act, node.dataset.vibe || "", node.dataset.index || "", node.dataset.quality || "", node.dataset.method || "", node.dataset.step || "", node.dataset.value || ""].join(":");
}

// Nothing moves under you when the desk redraws. render() builds the desk anew from innerHTML, so without this a click
// in the scrolled inspector column (Foreshadow, Look) jumped the column to its top, and a row changing height above
// you (a note that grows, stills arriving while a grow runs) moved the page. Every scrolled panel gets its place back,
// and the row you were on (the one holding the focused control, else the one a third of the way down the window) is
// put back where it was on the screen.
const SCROLLERS = ".easy-side";
function anchorKey(node) {
  if (!node || node.nodeType !== 1) return "";
  if (node.id) return `#${CSS.escape(node.id)}`;
  const d = node.dataset || {};
  if (d.tour) return `[data-tour="${CSS.escape(d.tour)}"]`;
  if (!d.act) return "";
  // a control: the very button clicked (Foreshadow's Trace, not the column it sits in; the vibe card picked, which moves
  // from More vibes into the grid, not whichever card takes its old place in the list)
  return `[data-act="${CSS.escape(d.act)}"]${d.value != null ? `[data-value="${CSS.escape(d.value)}"]` : ""}${d.vibe != null ? `[data-vibe="${CSS.escape(d.vibe)}"]` : ""}${d.index != null ? `[data-index="${CSS.escape(d.index)}"]` : ""}`;
}
function scrollerKey(node, seen) {
  const base = anchorKey(node) || `${node.tagName}.${node.className && node.className.baseVal == null ? node.className : ""}`;
  seen[base] = (seen[base] || 0) + 1;
  return `${base}@${seen[base]}`;
}
function rememberScrollers(root) {
  const out = {};
  const seen = {};
  for (const node of root.querySelectorAll("*")) {
    const key = scrollerKey(node, seen);
    if (node.scrollTop || node.scrollLeft) out[key] = [node.scrollTop, node.scrollLeft];
  }
  return out;
}
function restoreScrollers(root, saved) {
  if (!saved || !Object.keys(saved).length) return;
  const seen = {};
  for (const node of root.querySelectorAll("*")) {
    const at = saved[scrollerKey(node, seen)];
    if (at) {
      node.scrollTop = at[0];
      node.scrollLeft = at[1];
    }
  }
}
function rememberAnchor(app) {
  const focus = document.activeElement;
  let node = focus && focus !== document.body && app.contains(focus) ? focus : null;
  if (!node) node = document.elementFromPoint(Math.round(window.innerWidth * 0.4), Math.round(Math.min(window.innerHeight / 3, 320)));
  while (node && node !== app && !anchorKey(node)) node = node.parentElement;
  if (!node || node === app || !app.contains(node)) return null;
  const key = anchorKey(node);
  return { key, nth: [...app.querySelectorAll(key)].indexOf(node), top: node.getBoundingClientRect().top };
}
function restoreAnchor(app, anchor) {
  if (!anchor) return;
  const node = app.querySelectorAll(anchor.key)[Math.max(0, anchor.nth)];
  if (!node) return;
  const delta = node.getBoundingClientRect().top - anchor.top;
  if (Math.abs(delta) < 1) return;
  const box = node.closest(SCROLLERS);
  if (box === node) return;  // a scrolled panel itself keeps its own place (restoreScrollers)
  if (box) box.scrollTop += delta;
  else window.scrollBy(0, delta);
}

function rememberPlace() {
  const node = document.activeElement;
  const app = document.getElementById("app");
  const place = { y: window.scrollY || 0, key: placeKey(node), start: null, end: null };
  if (app) {
    place.scrollers = rememberScrollers(app);
    place.anchor = rememberAnchor(app);
  }
  if (node && node.selectionStart != null) {
    place.start = node.selectionStart;
    place.end = node.selectionEnd;
  }
  return place;
}

function restorePlace(place) {
  if (!place || document.body.dataset.tour === "1") return;
  if (place.y) window.scrollTo(0, place.y);
  const app = document.getElementById("app");
  if (app) {
    restoreScrollers(app, place.scrollers);
    restoreAnchor(app, place.anchor);
  }
  if (!place.key) return;
  let node = null;
  if (place.key.startsWith("#")) node = document.getElementById(place.key.slice(1));
  else {
    const parts = place.key.split(":");
    const act = parts[1];
    const value = parts.slice(7).join(":");  // a value may hold a colon (an aspect, 9:16)
    const same = [...document.querySelectorAll(`[data-act="${act}"]`)].filter((item) => {
      if (parts[2] && item.dataset.vibe !== parts[2]) return false;
      if (parts[3] && String(item.dataset.index || "") !== parts[3]) return false;
      if (parts[4] && item.dataset.quality !== parts[4]) return false;
      if (parts[5] && item.dataset.method !== parts[5]) return false;
      if (parts[6] && item.dataset.step !== parts[6]) return false;
      return true;
    });
    // the chip clicked keeps the focus (15 s, not the row's first chip, Full song), else the row's first as before
    node = same.find((item) => value && item.dataset.value === value) || same[0] || null;
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

// The screen render() last drew (view and phase). A click redraws the whole desk, and the fade-in on #app's children
// blanked it and slid it 4 px on every click; now it plays only when the screen changes.
let lastScreen = "";
// Where each page was scrolled when you left it. A tool page (Setup & models, Connect an AI) opens at its top and the
// desk comes back where you left it: the place kept across that switch named a control of the other page, so "Back to
// the desk" was put where the Setup link sits, at the desk's foot.
const pageScroll = {};

function render() {
  const place = rememberPlace();
  const app = document.getElementById("app");
  state.view = viewFromHash();
  const phase = (state.easy && state.easy.phase) || "";  // song, choose and vibe all draw the one desk
  const screen = `${state.view}:${["making", "result", "showcase"].includes(phase) ? phase : "desk"}`;
  if (screen !== lastScreen) app.dataset.enter = "1";
  else delete app.dataset.enter;
  const pageBefore = lastScreen.split(":")[0];
  const pageSwitch = !!lastScreen && pageBefore !== state.view;
  if (pageSwitch) pageScroll[pageBefore] = place.y;
  lastScreen = screen;
  // One desk: the stages (Song, Vibe, Prototype, Refine, Share) or a tool page. There is no second desk to switch to.
  app.innerHTML = (state.view === "setup" || state.view === "connect") ? renderTool(state.view) : renderEasy();
  // the stage strip lives in the toolbar, like the steps of a desktop tool, on every screen
  const strip = document.getElementById("stage-slot");
  if (strip) strip.innerHTML = state.easy ? easyCrumbs(Object.assign({}, state.easy, state.view === "simple" ? {} : { phase: "tool" })) : "";
  document.body.dataset.phase = state.view === "simple" ? ((state.easy && state.easy.phase) || "choose") : state.view;
  document.body.dataset.knobs = knobsFolded() ? "folded" : "open";
  saveEasy();
  paintJob();
  mountLive();
  scheduleSession();
  document.body.dataset.ready = "1";
  if (window.XENO_IDEAS) window.XENO_IDEAS.mount();
  if (window.XENO_KNOBS_MOUNT) window.XENO_KNOBS_MOUNT();  // the knob strip (ui_v6.js) in now, not a frame after the place is put back
  if (window.XENO_TUTORIAL) window.XENO_TUTORIAL.sync();
  scheduleOpener();
  if (pageSwitch) { if (document.body.dataset.tour !== "1") window.scrollTo(0, pageScroll[state.view] || 0); }  // the tour places itself
  else restorePlace(place);
  paintPlayhead();
  paintPending();
}

// Setup & models and Connect an AI as full pages on the desk (the "..." menu, the line under Make, #setup and #connect).
function renderTool(view) {
  const title = view === "setup" ? "Setup & models" : "Connect an AI";
  return `<div class="easy easy-tool">
    <div class="easy-tool-head">
      <button type="button" class="ghost easy-back" data-act="go" data-hash="simple">&larr; Back to the desk</button>
      <p class="eyebrow">Xenoform · ${esc(title)}</p>
    </div>
    ${view === "setup" ? renderSetup() : renderConnect()}
  </div>`;
}

function mountLive() {
  window.XENO_STATE = () => state;
  window.XENO_STEMS_FOR = (id) => stemsFor(id);  // the knob strip's Stem reactions summary mirrors the Stems line instead of polling for itself
  if (state && state.easy && state.easy.playedHere && document.getElementById("easy-screen")) {
    requestAnimationFrame(() => startLibraryCut());
  }
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

// The cut's guardrail report on its own screen, under the player: one summary line, the folded lines behind it. It was
// a bar under the header that only the Director desk showed, so a Simple cut never said what was clamped.
function guardDetails(job) {
  const lines = guardLines((job && job.guardrails && job.guardrails.messages) || []);
  if (!lines.length) return "";
  const qa = lines.filter((m) => m.startsWith("[qa]")).length;
  const clamps = lines.length - qa;
  const head = [clamps ? `${clamps} setting${clamps === 1 ? "" : "s"} adjusted` : "", qa ? `${qa} check${qa === 1 ? "" : "s"} flagged` : ""].filter(Boolean).join(" · ");
  return `<details class="guardnotes"><summary>Guardrails: ${esc(head)}</summary><ul>${lines.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></details>`;
}
// The knobs column folds to a slim tab on the cut's screen (remembered), so the video and the timeline get the width.
function knobsFolded() {
  try { return localStorage.getItem("xeno-knobs-folded") === "1"; } catch (err) { return false; }
}

// Changes waiting on a cut: the knob rows turned since the last re-cut (a set of rows, so three clicks on Look are one
// change) and the timeline's edits. One bar at the bottom of the window applies all of them in one re-cut from the
// cached morphs; the lane's Apply and the knobs' Re-cut used to be two buttons for the same thing (28 Oct).
// (Scenes is not here: a re-cut keeps the cut's stills, so a Scenes choice waits for the next render)
const KNOB_ACTS = { "easy-look": "Look", "easy-effect": "Effects", "easy-morph-timing": "Timing", "easy-foreshadow": "Foreshadow" };
function touchKnob(row) {
  if (!state.easy) return;
  state.easy.knobsTouched = Object.assign({}, state.easy.knobsTouched || {}, { [row]: 1 });
  paintPending();
}
document.addEventListener("xeno-knobs", () => {
  if (state && state.easy && state.easy.phase === "result") touchKnob("Knobs");
});
function pendingParts(easy) {
  const rows = Object.keys((easy && easy.knobsTouched) || {});
  const id = easyVideoId();
  const lane = state.lane && state.lane.id === id ? state.lane : null;
  const edits = lane ? timelineDirty(easy, lane) : 0;
  return { rows, edits };
}
function pendingCount(easy) {
  const { rows, edits } = pendingParts(easy);
  return rows.length + edits;
}
function pendingBar(easy) {
  if (!easy || easy.phase !== "result" || easy.showcase || !easyVideoId()) return "";
  const { rows, edits } = pendingParts(easy);
  const n = rows.length + edits;
  if (!n) return "";
  const what = [rows.length ? rows.join(", ") : "", edits ? `${edits} timeline edit${edits === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ");
  return `<div class="pending-bar" role="status">
      <span><b>${n} change${n === 1 ? "" : "s"} waiting</b> <span class="note">${esc(what)}</span></span>
      <button type="button" class="generate" data-act="easy-apply">Apply · re-cut</button>
      <span class="note">from the cached morphs, no GPU</span>
    </div>`;
}
function paintPending() {
  // docked on the body, outside #app: an animated ancestor there would make position:fixed sit mid-page
  let dock = document.getElementById("pending-dock");
  if (!dock) {
    dock = document.createElement("div");
    dock.id = "pending-dock";
    document.body.appendChild(dock);
  }
  dock.innerHTML = state && state.easy && state.view === "simple" ? pendingBar(state.easy) : "";
  const button = document.querySelector('[data-act="easy-recut-knobs"]');
  const n = state.easy ? pendingCount(state.easy) : 0;
  if (button) button.textContent = n ? `Apply ${n} change${n === 1 ? "" : "s"}` : "Re-cut with these knobs";
}

// The timeline's playhead: where the player is, over the shots, moving while it plays (the lane is a percentage of
// the cut's length, data-total on #lane-track).
let playheadFrame = 0;
function paintPlayhead() {
  const head = document.getElementById("lane-playhead");
  const track = document.getElementById("lane-track");
  const player = document.getElementById("player");
  if (!head || !track || !player) return;
  const total = Number(track.dataset.total) || player.duration || 1;
  const at = Math.max(0, Math.min(1, (player.currentTime || 0) / total));
  head.style.left = `${(100 * at).toFixed(3)}%`;
  head.classList.toggle("on", at > 0 || !player.paused);
}
function playheadLoop() {
  paintPlayhead();
  const player = document.getElementById("player");
  playheadFrame = player && !player.paused && !player.ended ? requestAnimationFrame(playheadLoop) : 0;
}
["play", "playing", "seeked", "timeupdate", "pause", "loadedmetadata"].forEach((type) => {
  document.addEventListener(type, (event) => {
    if (!event.target || event.target.id !== "player") return;
    if (!playheadFrame) playheadLoop();
  }, true);
});

// The making screen's live parts, painted in place on every poll: the step the render is on, and the chain once the
// render has picked it. That chain replaces the pre-Make preview, which never knew the stills Make grows for the line;
// the screen used to keep the preview's 41 stills up through a whole Final that rendered 15 (28 Oct).
const MAKING_STEP = { analyze: 0, draft: 1, morphs: 2, cut: 3, assemble: 3, card: 3, save: 3, qa: 3, done: 4 };
function paintMaking(job) {
  const at = MAKING_STEP[String((job.timing && job.timing.phase) || job.stage || "")];  // job_timing's canonical phase
  if (at != null) {
    document.querySelectorAll("#easy-happen li").forEach((li, i) => { li.className = i < at ? "done" : i === at ? "now" : "wait"; });
  }
  const chain = Array.isArray(job.chain) && job.chain.length ? job.chain : null;
  const label = document.getElementById("easy-chain-label");
  const text = document.getElementById("easy-chain");
  if (chain && label && text) {
    label.textContent = chain.every((c) => c.kind === "clip")  // a clips cut (clip_cut writes its clips' names)
      ? `Your clips: ${chain.length} stretches, ${Math.max(0, chain.length - 1)} morphs between them`
      : `The chain: ${chain.length} stills, ${Math.max(0, chain.length - 1)} morphs`;
    text.textContent = chain.map((s) => s.noun || "").filter(Boolean).join(" → ");
  }
}

function paintJob() {
  const slot = document.getElementById("easy-guard");
  if (slot) slot.innerHTML = guardDetails(state && state.job);
}

// The guardrail report, one line per distinct message. The server emits one line per clamped boundary and one per QA
// flag, which on a 103-shot song was fifty identical "match-cut already used 2x; this boundary is a clean beat cut" rows:
// identical lines fold into one with a count, and the QA's timed flags ("[qa] glitch at 1.5s") fold into one line a kind.
function guardLines(messages) {
  const counts = new Map();
  const flags = {};
  const kinds = [];
  (messages || []).forEach((raw) => {
    const text = String(raw == null ? "" : raw).trim();
    if (!text) return;
    const flag = text.match(/^\[qa\] ([a-z][a-z -]*?) at ([\d.]+s)$/);
    if (flag) {
      if (!flags[flag[1]]) {
        flags[flag[1]] = [];
        kinds.push(flag[1]);
      }
      flags[flag[1]].push(flag[2]);
      return;
    }
    counts.set(text, (counts.get(text) || 0) + 1);
  });
  const out = [];
  counts.forEach((n, text) => out.push(n > 1 ? `${text} (× ${n})` : text));
  kinds.forEach((kind) => {
    const at = flags[kind];
    const more = at.length > 8 ? ` and ${at.length - 8} more` : "";
    out.push(`[qa] ${at.length} ${kind} flag${at.length === 1 ? "" : "s"} at ${at.slice(0, 8).join(", ")}${more}`);
  });
  return out;
}

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
}

let ignoreJob = null;

// The bundled songs (GET /api/songs): six of the author's own Suno instrumentals in examples/songs/, shipped with their
// analyses, so a chip under Choose a song loads one at once. The list is fetched once, lazily, the way loadSetup fills
// state.setup; a failed fetch shows nothing. The row lands in its own slot (#bundled-songs), so nothing else redraws.
let songsAsking = false;
async function loadSongs() {
  if (!state || state.songs || songsAsking) return;
  songsAsking = true;
  try {
    const response = await api("/api/songs");
    const data = response.ok ? await response.json() : null;
    if (state) state.songs = (data && data.songs) || [];
  } catch (err) {
    if (state) state.songs = [];
  }
  songsAsking = false;
  const slot = document.getElementById("bundled-songs");
  if (slot && state && state.easy && !state.easy.song) slot.innerHTML = songsRow(state.easy);
}

function songClock(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  return `${Math.floor(safe / 60)}:${String(Math.floor(safe % 60)).padStart(2, "0")}`;
}

function songsRow(easy) {
  const songs = state && state.songs;
  if (!songs) {
    loadSongs();
    return "";
  }
  if (!songs.length) return "";
  // The on class matches the Bundled demo button's; both rows are drawn only while no song is chosen, so neither shows.
  const chips = songs.map((song) => `<button type="button" class="chip${easy.song === song.id ? " on" : ""}" data-act="easy-song" data-id="${esc(song.id)}" title="${esc(song.feel || "")}">${esc(song.title)}<small>${songClock(song.seconds)}</small></button>`).join("");
  return `<div class="song-shelf"><span class="shelf-label">Bundled songs</span><div class="toggle chips song-chips" role="group" aria-label="Bundled songs">${chips}</div></div>`;
}

// A chip: the song's shipped analysis comes back at once (POST /api/songs/load) and the desk adopts it as it adopts the
// demo. The chip says Loading… in its own text until the payload is in; nothing redraws before that.
async function useBundledSong(id) {
  const song = ((state && state.songs) || []).find((row) => row.id === id);
  if (!song || !state.easy) return;
  const safeId = window.CSS && CSS.escape ? CSS.escape(id) : id;
  const chip = document.querySelector(`[data-act="easy-song"][data-id="${safeId}"]`);
  if (chip) {
    chip.textContent = "Loading…";
    chip.disabled = true;
  }
  state.easy.song = song.id;
  state.easy.songLabel = song.title;
  state.easy.note = "";
  if (!state.easy.phase || state.easy.phase === "song" || state.easy.phase === "choose") setEasyPhase("vibe");
  if (state.audioId === `song-${song.id}`) {
    render();
    return;
  }
  let data = null;
  try {
    const response = await api("/api/songs/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: song.id }) });
    if (response.ok) data = await response.json();
  } catch (err) {
    data = null;
  }
  // Another chip, the demo or a file chosen while this one loaded: that choice owns the desk now, and this answer is
  // dropped, so the desk never names one song and holds another.
  if (!state || !state.easy || state.easy.song !== song.id) return;
  if (!data) {  // back to the song step, cleanly: no half-loaded song
    state.easy.song = "";
    state.easy.songLabel = "";
    state.easy.note = "That song did not load. Try again, or choose a file.";
    setEasyPhase("choose");
    render();
    return;
  }
  adoptSession(data);
  await settleCut({ full: true });
  loadSimpleOptions().then(() => render());
}

async function useDemoSong() {
  const note = document.getElementById("song-note");
  if (note) note.textContent = "Using the bundled demo, examples/demo.wav.";
  if (state && state.easy) {
    state.easy.song = "demo";
    state.easy.songLabel = "Bundled demo";
    state.easy.note = "";
    if (!state.easy.phase || state.easy.phase === "song" || state.easy.phase === "choose") state.easy.phase = "vibe";
  }
  if (!state || state.audioId === "demo") {
    render();
    return;
  }
  const response = await api("/api/demo");
  if (!response.ok) return;
  if (!state || !state.easy || state.easy.song !== "demo") return;  // a bundled song or a file was chosen meanwhile: it owns the desk
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
    // the machine check and any model download outlive a new song: Setup & models read "Checking this machine…"
    // for good after an upload, because the fresh state had dropped them and nothing asked again
    setup: previous ? previous.setup || null : null,
    songs: previous ? previous.songs || null : null,  // the bundled songs (GET /api/songs), fetched once a session
    downloads: previous ? previous.downloads || {} : {},
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
      : Object.assign({ song: "", songLabel: "", vibe: "", idea: "", ownFolder: "", ownId: "", ownNote: "", ownShapes: "", stillsNote: "", foreshadow: "auto", scenes: "off", phase: "song", note: "", playedHere: false,
          // the house (demo_house): 9:16 native, Dense, Draft, Beat FX, the house look, subject orbit, no end card
          energyPreset: "dense", aspect: "9:16", tier: "draft", fx: true, endCard: false, danceFx: "auto", stemOrbit: true },
        loadEasy()),
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
    stillsNote: previous ? previous.stillsNote || "" : "",
    score: previous ? previous.score || null : null,
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
  const player = document.getElementById("player");
  if (player) {
    const next = media(job.video);
    if (player.getAttribute("src") !== next) player.src = next;
  }
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
  }
  render();
}

async function shareCut(button) {
  if (!state) return;
  // A reopened cut (My videos) has no live job record: its id is the job folder, so Download shares that file.
  const jobId = (state.job && state.job.id) || (state.easy && state.easy.reopenId) || "";
  const job = jobId ? `?job=${encodeURIComponent(jobId)}` : "";
  if (button) button.classList.add("is-loading");
  try {
    const response = await api(`/api/share${job}`);
    if (!response.ok) {  // say why in words; a failed share used to leave the button as if nothing was pressed
      const body = await response.json().catch(() => ({}));
      state.easy.note = typeof body.detail === "string" ? body.detail : "The 720p cut did not build. Try Download instead.";
      render();
      return;
    }
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

// Send the make body. The Director desk's gates (approve the shot list, approve 1 or 2 test clips, a story that holds in
// one line) are gone with it: a Make is the Simple cut, which never rendered the storyboard they guarded.
async function generate() {
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
  if (state.easy && job.eta_s !== state.easy.lastEta) { state.easy.lastEta = job.eta_s; state.easy.jobAt = Date.now(); }
  if (state.easy && state.easy.phase === "making") {
    if (job.video) showEasyPreview(job.video);
    if (job.status === "done") {
      notifyReady(job, false);
      setEasyPhase("result");
      state.easy.playedHere = false;
      state.easy.warm = true;
      if (state.easy.recutting) {  // a re-cut or a swap: the lane reads the record again and a reopened player reloads
        state.easy.recutting = false;
        state.lane = null;
        state.easy.editUrl = "";  // the pack laid out the cut before this edit: Edit in Resolve makes the new one
        if (state.easy.reopenUrl) state.easy.reopenUrl = `${String(state.easy.reopenUrl).split("?")[0]}?v=${job.video_version || Date.now()}`;
      }
      const took = Number(job.took_s || job.seconds || 0);
      state.easy.took = took;
      state.easy.note = String(job.detail || "").startsWith("The animatic is ready")
        ? job.detail
        : took ? `Took ${clockText(took)}${tookBreakdown(job.breakdown)}.` : "Your cut is ready.";
      render();
      return;
    }
    if (job.status === "error" || job.status === "cancelled") {
      state.quality = "live";
      setEasyPhase("result");
      state.easy.playedHere = true;
      // say why: the error bar that named it lived on the Director desk, so a failed Simple cut used to say nothing
      const why = job.status === "error" ? String(job.error || job.detail || "").trim() : "";
      state.easy.note = why ? `The render stopped: ${why} Playing the pictures for this vibe instead.` : "Playing the pictures for this vibe.";
      if (job.status === "error") notifyReady(job, true); else tabTitle();
      state.easy.failed = job.status === "error";
      render();
      return;
    }
    const line = document.getElementById("easy-progress");
    if (line) line.textContent = easyProgressText(job);
    paintMaking(job);
  }
  paintJob();
  if (job.status === "running") setTimeout(() => poll(id), 400);
}

document.addEventListener("click", async (event) => {
  const el = event.target.closest("[data-act]");
  if (!el || !state) return;
  const act = el.dataset.act;
  if (KNOB_ACTS[act] && state.easy && state.easy.phase === "result" && el.closest(".easy-side")) touchKnob(KNOB_ACTS[act]);
  if (act === "palette") {
    openPalette();
  } else if (act === "palette-run") {
    runPalette(paletteRows[Number(el.dataset.index)]);
  } else if (act === "use-demo" || act === "easy-demo") {
    useDemoSong();
  } else if (act === "easy-song") {
    useBundledSong(el.dataset.id || "");
  } else if (act === "easy-own-stems-clear") {
    clearOwnStems();
  } else if (act === "easy-vibe") {
    if ((el.dataset.vibe || "") !== (state.easy.vibe || "")) {  // the pins name one vibe's stills: another vibe starts unpinned
      state.easy.pins = {};
      state.easy.chainPick = null;
    }
    state.easy.vibe = el.dataset.vibe || "";
    state.easy.note = "";
    if (state.easy.phase === "result" || state.easy.phase === "showcase") {
      if (!state.easy.song) {
        state.easy.note = "Choose a song, then Make.";
        setEasyPhase("choose");
      }
      // the card only selects; "Make it with ..." under the grid starts the render (one click on a thumbnail used to)
      render();
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
  } else if (act === "easy-film-pack") {
    pickFilmPack();
  } else if (act === "easy-seek") {
    const player = document.getElementById("player");
    if (player) {
      player.currentTime = Number(el.dataset.at) || 0;
      if (player.paused) player.play().catch(() => {});
    }
  } else if (act === "easy-grow") {
    growStills(false);
  } else if (act === "easy-grow-scenes") {
    growStills(false, "scene");
  } else if (act === "easy-make-shapes") {
    growStills(true);
  } else if (act === "easy-grow-stop") {
    api("/api/stills/stop", { method: "POST" }).then(() => loadStills(true));
  } else if (act === "easy-chain-slot") {
    const slot = Number(el.dataset.slot);
    state.easy.chainPick = state.easy.chainPick === slot ? null : slot;
    render();
  } else if (act === "easy-chain-cancel") {
    state.easy.chainPick = null;
    render();
  } else if (act === "easy-pin") {
    const pins = Object.assign({}, state.easy.pins || {});
    pins[String(Number(el.dataset.slot))] = el.dataset.file || "";
    state.easy.pins = pins;
    state.easy.chainPick = null;
    render();  // the pins are in the chain key, so the row reads the chain again with them
  } else if (act === "easy-unpin") {
    const pins = Object.assign({}, state.easy.pins || {});
    delete pins[String(Number(el.dataset.slot))];
    state.easy.pins = pins;
    render();
  } else if (act === "easy-chain-reset") {
    state.easy.pins = {};
    state.easy.chainPick = null;
    render();
  } else if (act === "easy-swap-mode") {
    state.easy.swapMode = !state.easy.swapMode;
    state.easy.swapSlot = null;
    render();
  } else if (act === "easy-swap-pick") {
    state.easy.swapSlot = Number(el.dataset.slot);
    const player = document.getElementById("player");
    if (player) player.currentTime = Number(el.dataset.at) || 0;
    render();
  } else if (act === "easy-swap-cancel") {
    state.easy.swapSlot = null;
    render();
  } else if (act === "easy-swap") {
    swapStill(easyVideoId(), Number(el.dataset.slot), el.dataset.file || "");
  } else if (act === "easy-tl-shot" || act === "easy-tl-bound") {
    // the timeline: a click opens the shot's drawer (a seam opens its Join tab) and seeks the player there (a little
    // before a seam)
    state.easy.tlPick = { kind: "shot", index: Number(el.dataset.index) };
    if (act === "easy-tl-bound") state.easy.tlTab = "join";
    state.easy.tlFor = easyVideoId();
    const player = document.getElementById("player");
    const at = Number(el.dataset.at) || 0;
    if (player) player.currentTime = act === "easy-tl-bound" ? Math.max(0, at - 0.6) : at;
    render();
  } else if (act === "easy-tl-tab") {
    state.easy.tlTab = el.dataset.value || "look";
    render();
  } else if (act === "easy-tl-step") {
    const lane = state.lane;
    const pick = state.easy.tlPick;
    if (lane && pick) {
      const next = Math.max(0, Math.min(lane.shots.length - 1, pick.index + Number(el.dataset.value)));
      state.easy.tlPick = { kind: "shot", index: next };
      const shot = lane.shots.find((x) => x.index === next);
      const player = document.getElementById("player");
      if (player && shot) player.currentTime = Number(shot.start) || 0;
    }
    render();
  } else if (act === "easy-tl-close") {
    state.easy.tlPick = null;
    render();
  } else if (act === "easy-tl-play") {
    setShotOverride(state.easy, state.lane, Number(el.dataset.index), "play", el.dataset.value);
    render();
  } else if (act === "easy-tl-look") {
    setShotOverride(state.easy, state.lane, Number(el.dataset.index), "look", el.dataset.value);
    render();
  } else if (act === "easy-tl-fx-clear") {
    setShotOverride(state.easy, state.lane, Number(el.dataset.index), "fx_intensity", null);
    render();
  } else if (act === "easy-tl-handoff") {
    // a Cut at a boundary is a Hold on the shot before it (docs/TIMELINE.md): one edit, seen from either side
    setShotOverride(state.easy, state.lane, Number(el.dataset.index) - 1, "play", el.dataset.value === "cut" ? "hold" : "morph");
    render();
  } else if (act === "easy-knobs-fold") {
    try { localStorage.setItem("xeno-knobs-folded", knobsFolded() ? "0" : "1"); } catch (err) {}
    render();
  } else if (act === "easy-tl-apply" || act === "easy-apply") {
    recutWithKnobs();
  } else if (act === "easy-tl-reset") {
    if (state.lane) {
      const tl = timelineState(state.easy, state.lane);
      tl.shots = {};
      tl.bounds = {};
      const persisted = Object.keys(state.lane.shot_overrides || {}).length + Object.keys(state.lane.boundary_overrides || {}).length;
      if (persisted) applyTimeline();
      else render();
    }
  } else if (act === "easy-tl-swap") {
    state.easy.swapMode = true;
    state.easy.swapSlot = Number(el.dataset.slot);
    state.easy.tlPick = null;
    render();
  } else if (act === "easy-tl-rerender") {
    rerenderShot(Number(el.dataset.index));
  } else if (act === "easy-tl-insert") {
    insertRun(Number(el.dataset.index));
  } else if (act === "easy-tl-dream") {
    dreamRun(Number(el.dataset.index));
  } else if (act === "easy-overlay") {
    state.easy.overlay = !state.easy.overlay;
    render();
  } else if (act === "easy-overlay-set") {
    state.easy.overlay = el.dataset.value === "on";
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
  } else if (act === "easy-cloud-final-ok") {
    state.easy.cloudFinalOk = !!el.checked;
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
  } else if (act === "easy-morph-style") {
    state.easy.morphStyle = ["auto"].concat(MORPH_STYLES).includes(el.dataset.value) ? el.dataset.value : "auto";
    render();
  } else if (act === "easy-tl-style") {
    rerenderShot(Number(el.dataset.index), el.dataset.value);
  } else if (act === "easy-effect") {
    // the Effects row is a set: a chip toggles its effect on or off
    const on = new Set(state.easy.effects || []);
    const id = el.dataset.value;
    if (EFFECTS.includes(id)) {
      if (on.has(id)) on.delete(id); else on.add(id);
    }
    state.easy.effects = EFFECTS.filter((x) => on.has(x));
    render();
  } else if (act === "easy-morph-timing") {
    state.easy.morphTiming = MORPH_TIMINGS.includes(el.dataset.value) ? el.dataset.value : "smooth";
    render();
  } else if (act === "easy-tl-move") {
    const lane = state.lane;
    const tl = timelineState(state.easy, lane);
    const i = Number(el.dataset.index);
    const j = i + Number(el.dataset.value);
    if (lane && j >= 0 && j < lane.shots.length) {
      const a = sourceOf(tl, i);
      const b = sourceOf(tl, j);
      setSource(state.easy, lane, i, b);
      setSource(state.easy, lane, j, a);
      state.easy.tlPick = { kind: "shot", index: j };  // the drawer follows the morph to its new slot
    }
    render();
  } else if (act === "easy-tl-dup") {
    const tl = timelineState(state.easy, state.lane);
    const i = Number(el.dataset.index);
    setSource(state.easy, state.lane, i + 1, sourceOf(tl, i));
    render();
  } else if (act === "easy-tl-drop") {
    const tl = timelineState(state.easy, state.lane);
    const i = Number(el.dataset.index);
    setShotOverride(state.easy, state.lane, i, "drop", (tl.shots[String(i)] || {}).drop ? null : true);
    render();
  } else if (act === "easy-tl-source-clear") {
    setShotOverride(state.easy, state.lane, Number(el.dataset.index), "source", null);
    render();
  } else if (act === "easy-tl-shift") {
    const v = Math.round(Number(el.dataset.value || 0) * 1000) / 1000;
    setBoundKey(state.easy, state.lane, Number(el.dataset.index), "shift", Math.abs(v) < 0.01 ? null : Math.max(-4, Math.min(4, v)));
    render();
  } else if (act === "easy-tl-effect") {
    // As the cut drops the shot's own set; a chip starts one (from the cut's) or toggles its effect in it
    const lane = state.lane;
    const i = Number(el.dataset.index);
    const o = (timelineState(state.easy, lane).shots[String(i)] || {});
    if (el.dataset.value === "cut") setShotOverride(state.easy, lane, i, "effects", null);
    else {
      const set = new Set(Array.isArray(o.effects) ? o.effects : (state.easy.effects || []).filter((x) => x !== "smear"));
      if (set.has(el.dataset.value)) set.delete(el.dataset.value); else set.add(el.dataset.value);
      setShotOverride(state.easy, lane, i, "effects", EFFECTS.filter((x) => set.has(x)));
    }
    render();
  } else if (act === "easy-tl-grade-clear") {
    setShotOverride(state.easy, state.lane, Number(el.dataset.index), "grade", null);
    render();
  } else if (act === "easy-tl-timing") {
    // a shot's own timing: an edit for Apply like its look (no GPU); "auto" is the cut's
    setShotOverride(state.easy, state.lane, Number(el.dataset.index), "timing", el.dataset.value);
    render();
  } else if (act === "easy-foreshadow") {
    state.easy.foreshadow = el.dataset.value || "auto";
    render();
  } else if (act === "easy-scenes") {
    state.easy.scenes = ["off", "mix", "only"].includes(el.dataset.value) ? el.dataset.value : "off";
    state.easy.scenesChosen = true;  // picked by hand: the idea line no longer turns Off into Mix
    render();
  } else if (act === "easy-source") {
    const from = morphSource(state.easy);
    const to = el.dataset.value === "clips" ? "clips" : "objects";
    if (from !== to) {
      // Your images and Your clips each keep their own folder and note: the film pack picked for clips used to show
      // under Your images ("The free film pack: 24 clips ...") once the row went back to Objects
      const kept = state.easy.ownBySource || (state.easy.ownBySource = {});
      kept[from] = { folder: state.easy.ownFolder || "", id: state.easy.ownId || "", note: state.easy.ownNote || "" };
      const back = kept[to] || {};
      state.easy.ownFolder = back.folder || "";
      state.easy.ownId = back.id || "";
      state.easy.ownNote = back.note || "";
    }
    state.easy.morphSource = to;
    render();
  } else if (act === "easy-orbit") {
    state.easy.stemOrbit = el.dataset.value !== "off";
    render();
  } else if (act === "easy-midi") {
    openMidiDrawer();
  } else if (act === "easy-morphs-auto") {
    state.easy.morphs = "auto";
    render();
  } else if (act === "easy-vertical") {
    state.easy.vertical = el.dataset.value === "crop" ? "crop" : "native";
    render();
  } else if (act === "easy-tier") {
    state.easy.tier = ["final", "fast", "cloud"].includes(el.dataset.value) ? el.dataset.value : "draft";
    state.easy.cloudFinalOk = false;  // spending credits is confirmed afresh each time Cloud Final is picked
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
  } else if (act === "easy-edit-open") {
    easyEditOpen();
  } else if (act === "easy-edit") {
    easyEdit();
  } else if (act === "easy-batch-n") {
    state.easy.batchN = [1, 3, 5, 10].includes(Number(el.dataset.value)) ? Number(el.dataset.value) : 3;
    saveEasy();
    render();
  } else if (act === "easy-batch-vary") {
    state.easy.batchVary = el.dataset.value || "seed";
    saveEasy();
    render();
  } else if (act === "easy-batch") {
    easyBatch(el);
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
    state.easy.knobsTouched = {};
    if (row.vibe && vibeById(row.vibe)) state.easy.vibe = row.vibe;
    state.easy.resultVibe = state.easy.vibe;
    state.easy.madeTier = row.tier || "draft";  // the Render row offers Final for a Draft; a saved cut's length is not known
    state.easy.madeLength = null;
    state.easy.failed = false;
    state.easy.reopenUrl = row.url;
    // Download / Share cut read the job id from here; a job record is not needed for a saved file.
    state.job = { id: row.id, status: "done", stage: "done", progress: 1, video: row.url, reopened: true };
    state.easy.recipe = row.recipe || "";
    state.easy.took = Number(row.seconds || 0);  // the desk knows how long a saved cut took (took.json): say so on reopen too
    state.easy.note = row.seconds ? `Took ${clockText(Number(row.seconds))}.` : "";
    state.easy.hookUrl = row.hook ? `/api/videos/${row.id}/hook.mp4` : "";
    state.easy.hookInfo = "";
    state.easy.editUrl = "";
    state.easy.showcase = false;
    state.easy.playedHere = false;
    setEasyPhase("result");
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
    // the file itself, at the size it was rendered (Share cut is the 720p copy for a post; Download used to be that too)
    const id = easyVideoId();
    if (!id) return;
    const link = document.createElement("a");
    link.href = media(`/api/videos/${encodeURIComponent(id)}/video`);
    link.download = `xenoform-${(state.easy && (state.easy.resultVibe || state.easy.vibe)) || "cut"}-${id}.mp4`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } else if (act === "easy-render-full" || act === "easy-render-final") {
    // Render, after the prototype: the cut's own vibe, then the whole song (Length: Full song, kept) or this span at Final
    if (!state.easy.song) {
      state.easy.note = "Choose the song again, then render.";
      setEasyPhase("choose");
      render();
      return;
    }
    if (state.easy.resultVibe && vibeById(state.easy.resultVibe)) state.easy.vibe = state.easy.resultVibe;
    const cutLane = state.lane && state.lane.id === easyVideoId() ? state.lane : null;
    if (cutLane && cutLane.source) state.easy.morphSource = cutLane.source === "clips" ? "clips" : "objects";  // a clips cut renders as one
    if (act === "easy-render-full") state.easy.lengthS = 0;
    else {
      state.easy.lengthS = Number(state.easy.madeLength) || 0;
      state.easy.tier = "final";
      // Final keeps the prototype's objects: every slot of this cut's chain (swaps included) is pinned, so the sharp
      // version morphs through the stills you approved instead of a fresh pick (the pick favours the least-used stills)
      const lane = state.lane && state.lane.id === easyVideoId() ? state.lane : null;
      const kept = lane && Array.isArray(lane.stills) ? lane.stills.filter((s) => s && s.file && s.index != null) : [];
      if (kept.length) {
        state.easy.pins = {};
        kept.forEach((s) => { state.easy.pins[String(s.index)] = s.file; });
      }
      // and its morphs change as they did: the style each shot was rendered in (the timeline's per-shot choices too);
      // the engine takes the list only when the Final plans the same shots (morph_style.for_cut)
      if (lane && Array.isArray(lane.shots) && lane.shots.length) state.easy.carryStyles = lane.shots.map((s) => s.style || "melt");
    }
    loadSimpleOptions().then(() => easyMake()).finally(() => { if (state && state.easy) state.easy.carryStyles = null; });
  } else if (act === "easy-hero-clear") {
    state.heroId = "";
    state.heroUrl = "";
    render();
  } else if (act === "easy-share") {
    if (state.easy && state.easy.playedHere) {
      state.easy.note = "This cut is the pictures on screen. A file needs ComfyUI.";
      const note = document.getElementById("easy-note");
      if (note) note.textContent = state.easy.note;
      return;
    }
    shareCut(el);
  } else if (act === "easy-step") {
    if (el.dataset.step === "song") {
      state.easy.song = "";
      state.easy.songLabel = "";
    }
    setEasyPhase("choose");
    render();
  } else if (act === "easy-stop") {
    if (state.job && state.job.status === "running" && state.job.id) {
      ignoreJob = state.job.id;
      api(`/api/jobs/${state.job.id}/cancel`, { method: "POST" }).catch(() => {});
    }
    setEasyPhase("choose");
    state.easy.note = "Stopped. Anything still queued on the GPU was cancelled.";
    render();
  } else if (act === "easy-showcase") {
    state.easy.playedHere = false;
    setEasyPhase("showcase");
    state.easy.note = "Made earlier with the same engine on one RTX 3080 Ti, open weights, cut to the bar of our own track. Back to the song, pick a vibe, then Make: a 30 s cut takes a few minutes on a 12 GB GPU, a full song about twenty, each Polly shot about eight.";
    render();
    const player = document.getElementById("player");
    if (player && player.play) player.play().catch(() => {});
  } else if (act === "easy-again") {
    state.easy.note = "";
    setEasyPhase("choose");
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else if (act === "easy-crumb") {
    const step = el.dataset.step || "song";
    // Share (and Refine) live on the cut's screen: scroll there; Song, Vibe and Prototype are the first screen
    const onCut = step === "share" || step === "refine";
    if (!onCut && (state.easy.phase === "result" || state.easy.phase === "showcase")) {
      state.easy.note = "";
      setEasyPhase("choose");
      render();
    }
    const where = { song: "[data-tour=easy-song]", vibe: "[data-tour=easy-vibe]", make: "[data-tour=easy-make]", share: "#easy-share", refine: ".shots-lane, .tl-panel" };
    const target = document.querySelector(where[step] || where.make);
    if (target && target.scrollIntoView) target.scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (act === "easy-recut-knobs") {
    recutWithKnobs();
  } else if (act === "go") {
    const menu = el.closest("details.more-menu");
    if (menu) menu.open = false;
    const hash = "#" + String(el.dataset.hash || "simple");
    if ((location.hash || "#simple") === hash) render();
    else location.hash = hash.slice(1);
  } else if (act === "check-extra") {
    loadSetup().then(() => {
      if (state.view === "setup") render();
    });
  } else if (act === "download-model") {
    downloadModel(el.dataset.id);
  } else if (act === "copy-job") {
    copyText(state.job && state.job.diagnostics ? state.job.diagnostics : state.job && state.job.error);
  } else if (act === "open-drop") {
    openDrop();
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
  } else if (target.id === "tl-fx") {
    // the timeline's per-shot FX intensity: the readout follows the thumb, the lane redraws on change
    setShotOverride(state.easy, state.lane, Number(target.dataset.index), "fx_intensity", Math.round(Number(target.value) * 1000) / 1000);
    const readout = document.getElementById("tl-fx-readout");
    if (readout) readout.textContent = Number(target.value).toFixed(2);
  } else if (target.classList && target.classList.contains("tl-grade-in")) {
    // a shot's Colour slider: the override follows the thumb (0 drops the key), the readout too; the lane redraws on change
    const i = Number(target.dataset.index);
    const o = timelineState(state.easy, state.lane).shots[String(i)] || {};
    const g = Object.assign({}, o.grade || {});
    const v = Math.round(Number(target.value) * 1000) / 1000;
    if (Math.abs(v) < 1e-3) delete g[target.dataset.key]; else g[target.dataset.key] = v;
    setShotOverride(state.easy, state.lane, i, "grade", Object.keys(g).length ? g : null);
    const readout = target.parentElement && target.parentElement.querySelector("b");
    if (readout) readout.textContent = v ? `${v > 0 ? "+" : ""}${target.dataset.key === "hue" ? Math.round(v) + "°" : v.toFixed(2)}` : "0";
  } else if (target.id === "easy-idea") {
    state.easy.idea = target.value;
    scheduleIdea();  // what the line was read as (scenes, objects, Polly) shows under it as it is typed
    if (state.easy.song && state.easy.vibe) scheduleChain(chainKey());  // the idea line moves the picks: the Chain row follows
  } else if (target.id === "easy-own-shapes") {
    state.easy.ownShapes = target.value;
    state.easy.stillsNote = "";
  } else if (target.id === "easy-own-folder") {
    state.easy.ownFolder = target.value;
    state.easy.ownId = "";  // one source at a time: a typed folder replaces dropped files
    state.easy.ownNote = "";
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!state) return;
  if (target.id === "tl-dress") {  // the timeline: what dresses this boundary (a transition, a boundary kind, none, auto)
    setBoundOverride(state.easy, state.lane, Number(target.dataset.index), target.value);
    render();
  } else if (target.id === "tl-fx" || (target.classList && target.classList.contains("tl-grade-in"))) {
    render();
  } else if (target.dataset.act === "easy-cut-plan") {
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
  } else if (target.dataset.act === "easy-own-stems") {
    uploadOwnStems(Array.from(target.files || []));
    target.value = "";  // the same files can be picked again after an error
  } else if (target.id === "hero-file" && target.files && target.files[0]) {
    uploadHero(target.files[0]);
  } else if ((target.id === "song-file" || target.id === "easy-file") && target.files[0]) {
    uploadSong(target.files[0]);
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

document.getElementById("copy-diagnostics").addEventListener("click", () => {
  copyDiagnostics();
});

document.addEventListener("xeno-tour-step", () => {
  if (state) render();
});

document.addEventListener("xeno-tour-end", () => {
  if (state) render();
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

let paletteRows = [];

// Ctrl K: every button and link on the desk as it is drawn now, searchable by its words.
function paletteControls() {
  const rows = [];
  const seen = new Set();
  document.querySelectorAll("button[data-act], a.ghost[href], .more-panel button").forEach((node) => {
    if (node.closest("#command-palette")) return;
    const label = (node.innerText || node.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    if (!label || label.length > 90) return;
    const row = {
      kind: "control",
      label,
      blurb: "",
      act: node.dataset.act || "",
      step: node.dataset.step || "",
      value: node.dataset.value || "",
      id: node.id || "",
      href: node.getAttribute("href") || "",
    };
    const key = [row.act, row.step, row.value, row.id, row.href, row.label].join("|");
    if (seen.has(key)) return;
    seen.add(key);
    rows.push(row);
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
  if (!row || !state || row.act === "palette") return;
  if (row.id) {
    const node = document.getElementById(row.id);
    if (node) node.click();
    return;
  }
  if (row.act) {
    const node = [...document.querySelectorAll(`[data-act="${row.act}"]`)].find((item) => {
      if (item.closest("#command-palette")) return false;
      if (row.step && item.dataset.step !== row.step) return false;
      if (row.value && item.dataset.value !== row.value) return false;
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
    const make = document.querySelector("[data-act=easy-make]");
    if (make) make.click();
    return;
  }
  if (event.key === "Escape") {
    if (touring) return;
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
    }
  }
});

document.getElementById("open-about").addEventListener("click", () => {
  document.getElementById("about").showModal();
});

const paletteForm = document.querySelector("#command-palette form");
if (paletteForm) paletteForm.addEventListener("submit", (event) => event.preventDefault());

document.getElementById("open-settings").addEventListener("click", () => {
  if (!state) return;
  const menu = document.querySelector("details.more-menu");
  if (menu) menu.open = false;
  document.getElementById("endpoint").value = state.endpoint || "";
  document.getElementById("addons").checked = !!state.addons;
  const paid = document.getElementById("paid-cloud");
  if (paid) {
    paid.checked = !!state.paidCloud;
    paid.disabled = state.paidCloudEnv === "on" || state.paidCloudEnv === "off";
    const why = document.getElementById("paid-cloud-env");
    if (why) why.textContent = state.paidCloudEnv ? `Set by XENO_PAID_CLOUD=${state.paidCloudEnv === "on" ? "1" : "0"} when the desk started.` : "";
  }
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
  state.endpoint =document.getElementById("endpoint").value.trim() || "http://127.0.0.1:8188";
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
  if (!state) return;
  state.comfyOk = ok;
}

// The logo is the home button: back to the song screen, from anywhere (a running job keeps its making screen).
const brandLink = document.querySelector(".brand");
if (brandLink) {
  brandLink.addEventListener("click", (event) => {
    if (!state || !state.easy) return;
    event.preventDefault();
    // from a tool page (#setup, #connect) push the desk first, so Back returns to the page you left
    if (viewFromHash() !== "simple") {
      try { history.pushState(null, "", "#simple"); } catch (err) { location.hash = "simple"; }
    }
    if (state.easy.phase !== "making") {
      state.easy.note = "";
      setEasyPhase("choose");
    }
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

window.addEventListener("hashchange", () => {
  if (!state) return;
  if (viewFromHash() === "simple" && state.easy) easyPhaseFromHash();
  render();
});

// The free film pack on the Setup page (xenoform.film_pack, state.setup.film_pack): a card like a model's. Its Download
// goes through the same route as a model's (POST /api/setup/download {id: "film-pack"}), so downloadModel and pollDownload
// drive it unchanged; the folder path stays in the detail. Download again fetches only what a grown list still lacks, a
// clip whose times moved (pack.stale) or a broken file, so it carries no size. An empty or unreadable list has no button.
// The status line and the bar carry ids (dl-status-<id>, dl-track-<id>) so pollDownload rewrites them in place while it runs.
function filmPackCard(pack) {
  if (!pack || !pack.id) return "";
  const job = (state.downloads || {})[pack.id] || {};
  const running = job.status === "running";
  const width = Math.round((job.progress || 0) * 100);
  const stale = Number(pack.stale || 0);
  const status = running
    ? job.detail || "Downloading"
    : job.status === "error"
      ? job.detail || job.error
      : pack.present
        ? `${pack.count} clips in place${stale ? `, ${stale} cut with older times (Download again remakes ${stale === 1 ? "it" : "them"})` : ""}`
        : pack.count
          ? `${pack.count} of ${pack.total} clips here`
          : "Optional";
  const label = running ? "Downloading" : pack.present ? "Download again" : `Download · ${esc(pack.size_label)}`;
  const button = pack.total
    ? `<button type="button" class="${pack.present ? "ghost" : "generate"}${running ? " is-loading" : ""}" data-act="download-model" data-id="${esc(pack.id)}" ${running ? "disabled" : ""}>${label}</button>`
    : "";
  return `<article class="model-card film-pack">
    <header><strong>${esc(pack.name)}</strong><span>${esc(pack.badge || "Clips")}</span></header>
    <p>${esc(pack.detail)}</p>
    <p class="status" id="dl-status-${esc(pack.id)}">${esc(status)}</p>
    ${running ? `<div class="track" id="dl-track-${esc(pack.id)}"><span style="width:${width}%"></span></div>` : ""}
    ${button}
  </article>`;
}

function renderSetup() {
  const setup = state.setup;
  if (!setup) {
    // never wait on a check nobody started: ask now, and say so if the desk does not answer
    if (!setupAsking) {
      setupAsking = true;
      loadSetup().then(() => {
        setupAsking = false;
        if (!state.setup) state.setup = { failed: true };
        if (state.view === "setup") render();
      });
    }
    return `<section class="panel"><p class="boot">Checking this machine…</p></section>`;
  }
  if (setup.failed) {
    return `<section class="panel"><p class="boot">The desk did not answer the machine check.</p>
      <button type="button" class="ghost" data-act="check-extra">Check again</button></section>`;
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
        <p class="status"><span id="dl-status-${esc(model.id)}">${esc(status)}</span>${model.filename ? ` · ${esc(model.filename)}` : ""}</p>
        ${picker}
        ${running ? `<div class="track" id="dl-track-${esc(model.id)}"><span style="width:${width}%"></span></div>` : ""}
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
      <p class="note">${esc(setup.checked || "")}</p>
      <p class="note">${esc(setup.disk ? setup.disk.free_label : "")} on the models drive. ${esc(setup.try_it || "")}</p>
      <p class="note">${esc((setup.stems || {}).detail || "")}</p>
    </section>
    <section class="panel models">${cards}</section>
    ${setup.film_pack ? `<section class="panel models">${filmPackCard(setup.film_pack)}</section>` : ""}
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
      <p class="note">Frame fill (${esc(setup.interpolate || "minterpolate")}) runs on its own when the QA pass finds judder; there is nothing to switch on. Live+AI and TensorRT stay off the base install.</p>
      <button type="button" class="ghost" data-act="check-extra">Check again</button>
    </section>
  </div>`;
}

let setupAsking = false;
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
  // worded for the Morph row in use: an object cut takes the images, a clips cut the clips, never both
  const clipsCut = morphSource(state.easy) === "clips";
  const n = Number(clipsCut ? data.clips : data.images) || 0;
  const left = Number(clipsCut ? data.clips_left : data.images_left) || 0;
  state.easy.ownNote = clipsCut
    ? (n ? `${n} clip${n === 1 ? "" : "s"} here. They play in turn, each morphing into the next.` : "No clips came with those files (mp4, mov or webm).")
    : (n ? `${n} image${n === 1 ? "" : "s"} here. They lead the morphs, in name order.` : "No images came with those files. Clips go under Morph > Your clips.");
  if (left) state.easy.ownNote += ` ${left} left out: a cut takes ${clipsCut ? data.max_clips : data.max_images} at most.`;
  render();
}

// The Stems line under the song. Every song is split in the background (GET /api/stems/for/<id>), and stems you
// already have go in through the same line (POST /api/stems/own; Back to Demucs is POST /api/stems/own/clear). While
// the split runs the line is polled every 2 s and rewrites its own text by id; the desk is redrawn only when the
// status changes shape (done, error, your own stems in use), so nothing flickers or scrolls. The poll stops when the
// song changes or the line leaves the screen, and never runs without a song.
let stemsTimer = null;
let stemsAsking = false;
let stemsSeq = 0;      // each ask is numbered: an answer to an older ask (the song changed, your stems were just posted) is dropped
let stemsPending = 0;  // the ask in flight, so a redraw meanwhile does not start a second poll chain
const STEMS_NOTE_MS = 10000;  // a refusal stays on the line this long; the split's poll goes on under it

// The Fine-tune Stem reactions lanes (ui_v6.js) follow this line: one lane per stem in use, the split's or your own.
function tellKnobsStems(st) {
  try { if (window.XENO_STEMS_UPDATE) window.XENO_STEMS_UPDATE(st.audioId, st); } catch (err) { /* no knob strip on this page */ }
}

function stemsFor(id) {
  return state && state.stems && state.stems.audioId === id ? state.stems : null;
}

function stemsBusy(st) {
  return !!st && (st.status === "queued" || st.status === "running");
}

function stemsShape(st) {
  return st ? `${stemsBusy(st) ? "busy" : st.status}|${st.own ? "own" : ""}|${(st.stems || []).join(",")}|${st.note || ""}` : "";
}

// Whether Back goes to Demucs or to the band split: what the split used before your stems (split_engine), else Setup.
function splitIsDemucs(st) {
  const was = String((st && st.split_engine) || "");
  if (was.startsWith("demucs")) return true;
  if (was === "librosa" || was === "bands") return false;
  return !!(state && state.setup && state.setup.stems && state.setup.stems.engine === "demucs");
}

function stemsText(st) {
  if (!st) return "Stems: looking…";
  if (st.note) return st.note;
  const names = st.stems || [];
  const engine = String(st.engine || "");
  const plural = names.length === 1 ? "" : "s";
  if (stemsBusy(st)) {
    const secs = st.seconds != null ? ` ${Math.round(Number(st.seconds) || 0)} s` : "";
    if (st.own) return `Stems: reading your ${names.length} stem${plural}…${secs}`;
    if (engine.startsWith("demucs") || (engine === "auto" && splitIsDemucs(st))) return `Stems: splitting with Demucs…${secs}`;
    return `Stems: splitting (band split)…${secs}`;
  }
  if (st.status === "done") {
    if (st.own) return `${names.length} stem${plural} of your own: ${names.slice(0, 3).join(", ")}${names.length > 3 ? "…" : ""}`;
    return `${names.length} stem${plural} from ${engine.startsWith("demucs") ? "Demucs" : "the band split"}: ${names.join(", ")}`;
  }
  if (st.status === "error") {
    if (st.own) return `Stems: your stems could not be read (${st.error || "the build failed"})`;
    return `Stems: not split (${st.error || "the split failed"})`;
  }
  return "Stems: not split";
}

function stemsLine() {
  if (!state || !state.audioId) return "";
  const st = stemsFor(state.audioId);
  // ask once after a load, and pick the poll up again when the line comes back on screen mid-split
  if ((!st || (stemsBusy(st) && !stemsTimer && !stemsPending)) && !stemsAsking) {
    stemsAsking = true;
    setTimeout(() => { stemsAsking = false; loadStems(true); }, 0);
  }
  const back = st && st.own
    ? ` <button type="button" class="text" data-act="easy-own-stems-clear">${splitIsDemucs(st) ? "Back to Demucs" : "Back to the split"}</button>`
    : "";
  return `<p class="note stems-line" id="stems-line"><span class="stems-text">${esc(stemsText(st))}</span> <label class="text">Use your own stems<input type="file" multiple accept="audio/*,.wav,.mp3,.flac,.ogg,.aiff,.m4a" data-act="easy-own-stems" hidden></label>${back}</p>`;
}

function paintStemsText(text) {
  const line = document.getElementById("stems-line");
  const span = line && line.querySelector(".stems-text");
  if (span) span.textContent = text;
  return !!span;
}

async function loadStems(force) {
  if (stemsTimer) { clearTimeout(stemsTimer); stemsTimer = null; }
  if (!state || !state.audioId || !state.easy || !state.easy.song) return;
  const id = state.audioId;
  const before = stemsFor(id);
  if (!force && before && !stemsBusy(before)) return;
  const seq = ++stemsSeq;
  stemsPending = seq;
  let st;
  try {
    const res = await api(`/api/stems/for/${encodeURIComponent(id)}`);
    const data = await res.json().catch(() => ({}));
    st = res.ok ? data : { status: "error", error: data.detail || "the desk did not answer" };
  } catch (err) {
    st = { status: "error", error: "the desk did not answer" };
  } finally {
    if (stemsPending === seq) stemsPending = 0;
  }
  if (!state || state.audioId !== id) return;  // the song changed while we asked
  if (seq !== stemsSeq) return;  // a newer ask, a pick or a clear took over while we asked
  st.audioId = id;
  if (before && before.note && Date.now() - (before.noteAt || 0) < STEMS_NOTE_MS) {  // a refusal stays readable while the split goes on under it
    st.note = before.note;
    st.noteAt = before.noteAt;
  }
  state.stems = st;
  tellKnobsStems(st);
  const line = document.getElementById("stems-line");
  if (stemsBusy(st) && line) stemsTimer = setTimeout(() => { stemsTimer = null; loadStems(true); }, 2000);
  else if (line && st.note && st.noteAt) stemsTimer = setTimeout(() => { stemsTimer = null; loadStems(true); }, Math.max(500, STEMS_NOTE_MS - (Date.now() - st.noteAt)));  // then the status comes back
  if (line && stemsShape(before) === stemsShape(st)) {
    paintStemsText(stemsText(st));  // in flight: only the seconds move, so the line is rewritten where it is
    return;
  }
  if (line && !before && !st.own) {
    paintStemsText(stemsText(st));  // the first look after a load: the same controls, only the text
    return;
  }
  if (line) render();
}

async function uploadOwnStems(files) {
  if (!files.length || !state || !state.audioId) return;
  const id = state.audioId;
  if (stemsTimer) { clearTimeout(stemsTimer); stemsTimer = null; }
  stemsSeq += 1;  // an answer on its way is about the stems before this pick
  stemsPending = 0;
  paintStemsText(`Stems: reading your ${files.length} file${files.length === 1 ? "" : "s"}…`);
  const body = new FormData();
  body.append("audio_id", id);
  files.forEach((file) => body.append("files", file));
  let data = {};
  let ok = false;
  try {
    const response = await api("/api/stems/own", { method: "POST", body });
    data = await response.json().catch(() => ({}));
    ok = response.ok;
  } catch (err) {
    data = { detail: "The desk did not answer." };
  }
  if (!state || state.audioId !== id) return;
  if (!ok) {
    const was = stemsFor(id) || { status: "none" };
    state.stems = { ...was, audioId: id, note: data.detail || "Those stems did not load.", noteAt: Date.now() };
    paintStemsText(state.stems.note);
    // the split's poll goes on under the refusal, and the line comes back to the status once the words have been read
    stemsTimer = setTimeout(() => { stemsTimer = null; loadStems(true); }, stemsBusy(was) ? 2000 : STEMS_NOTE_MS);
    return;
  }
  state.stems = { ...data, audioId: id };
  tellKnobsStems(state.stems);
  render();  // the line's controls change; stemsLine() then starts the one poll chain
}

async function clearOwnStems() {
  if (!state || !state.audioId) return;
  const id = state.audioId;
  if (stemsTimer) { clearTimeout(stemsTimer); stemsTimer = null; }
  stemsSeq += 1;
  stemsPending = 0;
  paintStemsText("Stems: back to the split…");
  let data = {};
  let ok = false;
  try {
    const response = await api("/api/stems/own/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ audio_id: id }) });
    data = await response.json().catch(() => ({}));
    ok = response.ok;
  } catch (err) {
    data = { detail: "The desk did not answer." };
  }
  if (!state || state.audioId !== id) return;
  state.stems = ok ? { ...data, audioId: id } : { ...(stemsFor(id) || { status: "none" }), audioId: id, note: data.detail || "The split did not come back.", noteAt: Date.now() };
  tellKnobsStems(state.stems);
  render();  // stemsLine() starts the poll when the split was queued again
  if (!ok) stemsTimer = setTimeout(() => { stemsTimer = null; loadStems(true); }, STEMS_NOTE_MS);
}

// The free film pack as this cut's clips (xenoform.film_pack): the folder Setup & models filled from archive.org. Whether
// it is there comes from the Setup check when the page has it, else from GET /api/film_pack, asked once and again after a
// download. Present: the pack's folder is the clips folder (remembered like any folder). Not there: the note points at Setup.
async function pickFilmPack() {
  if (!state.easy) return;
  let pack = state.setup && state.setup.film_pack;
  if (!pack) {
    if (!state.filmPack) {
      try {
        const response = await api("/api/film_pack");
        if (response.ok) state.filmPack = await response.json();
      } catch (err) {}
    }
    pack = state.filmPack;
  }
  if (!pack) {
    state.easy.ownNote = "The desk did not answer about the free film pack. Try again in a moment.";
    render();
    return;
  }
  const count = Number(pack.count || 0);
  if (!pack.present && count < 2) {  // a pack that came down in part still cuts (an archive.org window that failed is no dead end)
    state.easy.ownNote = state.easy.ownNoteSetup = `Download the free film pack in Setup & models first (about ${pack.size_label || "100 MB"}).`;
    render();
    return;
  }
  state.easy.ownFolder = pack.folder;
  state.easy.ownId = "";
  state.easy.ownNote = pack.present
    ? `The free film pack: ${pack.count} clips from ${pack.films} public-domain films. They play in turn, each morphing into the next.`
    : `The free film pack: ${count} of its ${pack.total} clips are here, and they play in turn, each morphing into the next. Download again in Setup & models fetches the rest.`;
  render();
}

// The library counts and the running grow (GET /api/stills); polled every few seconds while a grow runs.
let stillsTimer = null;
let wasRunning = false;
async function loadStills(force) {
  if (!state.easy || (!force && state.stills && !(state.stills.job && (state.stills.job.status === "running" || state.stills.job.status === "starting")))) return;
  try {
    const query = state.easy.vibe ? `?vibe=${encodeURIComponent(state.easy.vibe)}` : "";
    const res = await api(`/api/stills${query}`);
    if (!res.ok) return;
    const before = state.stills && state.stills.job;
    wasRunning = !!before && (before.status === "running" || before.status === "starting");
    state.stills = await res.json();
  } catch (err) {
    return;
  }
  const running = state.stills.job && (state.stills.job.status === "running" || state.stills.job.status === "starting");
  if (running && !stillsTimer) stillsTimer = setTimeout(() => { stillsTimer = null; loadStills(true); }, 3000);
  if (!running && state.stills.job && state.stills.job.status === "done" && state.easy) state.easy.stillsNote = "";
  // while the grow runs only its two lines change: rewrite them where they are, so nothing on the desk flickers
  const line = document.getElementById("library-status");
  const count = document.getElementById("library-count");
  if (running && wasRunning && line && count) {
    line.textContent = stillsStatus(state.easy);
    count.textContent = stillsCount(state.easy);
    return;
  }
  render();
}

async function growStills(own, kind) {
  if (!state.easy || !state.easy.vibe) return;
  const scenes = kind === "scene";
  const body = { vibe: state.easy.vibe, own: !!own && !scenes, kind: scenes ? "scene" : "object" };
  if (own && !scenes) body.nouns = state.easy.ownShapes || "";
  else if (scenes) body.count = Number((state.stills && state.stills.default_grow_scenes) || 8);
  else body.count = Number((state.stills && state.stills.default_grow) || 36);
  state.easy.stillsNote = own && !scenes ? "Rendering your shapes..." : scenes ? "Queueing the scenes..." : "Queueing the renders...";
  render();
  const response = await api("/api/stills/grow", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    state.easy.stillsNote = data.detail || "The stills did not start growing.";
    render();
    return;
  }
  state.easy.stillsNote = "";
  loadStills(true);
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
  const before = state.downloads[id] || {};
  state.downloads[id] = data;
  if (data.status === "running") {
    // while it runs only its status line and its bar change: rewrite them where they are (dl-status-<id>, dl-track-<id>),
    // so Setup is not redrawn twice a second under the user; the page is drawn again only when the job changes shape
    const line = document.getElementById(`dl-status-${id}`);
    const track = document.getElementById(`dl-track-${id}`);
    const bar = track && track.querySelector("span");
    if (before.status === "running" && line && bar) {
      line.textContent = data.detail || "Downloading";
      bar.style.width = `${Math.round((data.progress || 0) * 100)}%`;
    } else if (state.view === "setup") {
      render();
    }
    setTimeout(() => pollDownload(id), 500);
    return;
  }
  if (state.view === "setup") render();
  await loadSetup();
  if (id === "film-pack") state.filmPack = null;  // the Your clips row asks about the pack again
  if (state.view === "setup") render();
}

async function copyDiagnostics() {
  const response = await api("/api/diagnostics");
  const data = response.ok ? await response.json() : {};
  const job = state && state.job && state.job.diagnostics;
  await copyText([data.diagnostics, job].filter(Boolean).join("\n\n"));
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

function readMorphHit() {
  try {
    return localStorage.getItem("xeno-morph-hit") !== "0";
  } catch (err) {
    return true;
  }
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

async function boot() {
  try {
    localStorage.removeItem("xeno-advanced");  // the old Director desk switch; there is one desk now
  } catch (err) {}
  try {
    const response = await api("/api/demo");
    if (!response.ok) throw new Error("demo unavailable");
    adoptSession(await response.json());
    if (state && state.easy && viewFromHash() === "simple") easyPhaseFromHash();
    setInterval(pollAgent, 3000);
    await loadSetup();
    await settleCut({ full: true });
    refreshComfy();
    setInterval(refreshComfy, 8000);
    Promise.all([loadVideos(), loadVibes(), loadSimpleOptions()]).then(() => render());
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
  if (hint) hint.textContent = morphGuardText(n, state.easy.tier || "draft");
});
document.addEventListener("change", (ev) => {
  const el = ev.target;
  if (el && el.dataset && el.dataset.act === "easy-morphs") render();
});

// Fine-tune, Work in progress and More vibes remember whether they were open.
document.addEventListener("toggle", (ev) => {
  const el = ev.target;
  if (!el || !el.id) return;
  const key = { "fine-tune": "xeno-finetune", "wip-drawer": "xeno-wip", "more-vibes": "xeno-more-vibes" }[el.id];
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
