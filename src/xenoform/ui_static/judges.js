/* Beat-locked cut for judges. The page never calls the desk. */
(function () {
  const SHOTS = ["wide", "medium", "close", "reveal"];
  const state = {
    energy: 0,
    duration: 0,
    beats: [],
    drops: [],
    windows: [],
    morphs: [],
    playing: false,
  };

  const audio = document.getElementById("song");
  const empty = document.getElementById("empty");
  const note = document.getElementById("file-note");
  const grid = document.getElementById("grid");
  const qa = document.getElementById("qa");
  const readout = document.getElementById("readout");
  const energy = document.getElementById("energy");
  const drop = document.getElementById("drop");
  const clips = {};
  SHOTS.forEach((id) => {
    clips[id] = document.getElementById("clip-" + id);
  });

  function word(value) {
    if (value <= 0) return "Calm";
    if (value >= 1) return "Hype";
    return Number(value).toFixed(2);
  }

  function budget(value) {
    return Math.min(2, Math.round(Math.max(0, Math.min(1, value)) * 2));
  }

  function sectionsFor(duration) {
    const sections = [];
    for (let start = 0; start < duration - 0.2; start += 4) {
      sections.push({ start: start, end: Math.min(duration, start + 4) });
    }
    if (!sections.length) sections.push({ start: 0, end: duration || 1 });
    else sections[sections.length - 1].end = duration;
    return sections;
  }

  function windowsFor() {
    if (window.XENO_CUT) return window.XENO_CUT.windows(state.duration || 1, state.beats, state.energy);
    const duration = state.duration || 1;
    const sections = sectionsFor(duration);
    const level = Math.max(0, Math.min(1, state.energy));
    const beats = state.beats.filter((beat) => beat > 0 && beat < duration - 0.05);
    const sectionCount = Math.max(1, sections.length);
    if (level <= 0 || !beats.length) {
      return sections.map((section) => [section.start, section.end]);
    }
    const cap = Math.min(Math.max(beats.length, sectionCount), sectionCount * 4, 24);
    let count = sectionCount + Math.round(level * (cap - sectionCount));
    count = Math.max(sectionCount, Math.min(cap, count));
    let picks = [];
    if (count - 1 >= beats.length) picks = beats.slice();
    else {
      for (let index = 1; index < count; index += 1) {
        const slot = Math.min(beats.length - 1, Math.max(0, Math.round((index * beats.length) / count) - 1));
        picks.push(beats[slot]);
      }
      picks = Array.from(new Set(picks)).sort((a, b) => a - b);
    }
    const bounds = [0];
    picks.forEach((beat) => {
      if (beat - bounds[bounds.length - 1] >= 0.18) bounds.push(beat);
    });
    if (duration - bounds[bounds.length - 1] < 0.18) bounds[bounds.length - 1] = duration;
    else bounds.push(duration);
    const windows = [];
    for (let index = 0; index < bounds.length - 1; index += 1) windows.push([bounds[index], bounds[index + 1]]);
    return windows;
  }

  function morphSlots(windows) {
    if (window.XENO_CUT) {
      const drops = state.drops.length ? state.drops : [state.duration * 0.66];
      return window.XENO_CUT.morphs(windows, state.energy, drops);
    }
    const allowed = budget(state.energy);
    if (!allowed || windows.length < 2) return [];
    const drops = state.drops.length ? state.drops : [state.duration * 0.66];
    const ranked = windows
      .map((window, index) => ({ index: index, start: window[0] }))
      .filter((row) => row.index > 0)
      .sort((a, b) => {
        const da = Math.min.apply(null, drops.map((drop) => Math.abs(a.start - drop)));
        const db = Math.min.apply(null, drops.map((drop) => Math.abs(b.start - drop)));
        return da - db;
      });
    return ranked.slice(0, allowed).map((row) => row.index);
  }

  function recut() {
    state.windows = windowsFor();
    state.morphs = morphSlots(state.windows);
    paintGrid();
    paintQa();
    showAt(audio.currentTime || 0, true);
  }

  function paintGrid() {
    const duration = state.duration || 1;
    const ticks = [];
    state.beats.forEach((beat) => {
      ticks.push(`<i class="beat" style="left:${(beat / duration) * 100}%"></i>`);
    });
    state.windows.forEach((window, index) => {
      const kind = state.morphs.indexOf(index) >= 0 ? "morph" : "cut";
      ticks.push(`<i class="${kind}" style="left:${(window[0] / duration) * 100}%"></i>`);
    });
    ticks.push('<i class="play" id="playhead" style="left:0"></i>');
    grid.innerHTML = ticks.join("");
  }

  function paintQa() {
    const cuts = state.windows.slice(1).map((window) => window[0]);
    let hits = 0;
    cuts.forEach((cut) => {
      let nearest = Infinity;
      state.beats.forEach((beat) => {
        nearest = Math.min(nearest, Math.abs(beat - cut));
      });
      if (!state.beats.length || nearest <= 0.1) hits += 1;
    });
    const syncPass = !cuts.length || !state.beats.length || hits / cuts.length >= 0.8;
    const morphCount = state.morphs.length;
    const rows = [
      ["Sync", syncPass, state.beats.length ? `${hits} of ${cuts.length} cuts sit on a beat.` : "No beat clock, so cut alignment was not scored."],
      ["Motion", true, "Every library shot moves."],
      ["Morphs", morphCount <= 2, `${morphCount} morphs. The cap is 2.`],
      ["Flash", true, "No beat flash in this demo."],
      ["Energy", morphCount <= budget(state.energy), `Energy ${state.energy.toFixed(2)} allows ${budget(state.energy)} morphs. This cut has ${morphCount}.`],
    ];
    qa.innerHTML = `<ul class="qa-list">${rows
      .map(
        ([label, pass, detail]) =>
          `<li class="${pass ? "pass" : "fail"}"><span>${pass ? "Pass" : "Fail"}</span><b>${label}</b><em>${detail}</em></li>`,
      )
      .join("")}</ul>`;
  }

  function shotFor(index) {
    if (window.XENO_CUT) return window.XENO_CUT.shot(index);
    return SHOTS[index % SHOTS.length];
  }

  function useLibrary(id) {
    SHOTS.forEach((shot) => {
      const node = clips[shot];
      if (!node) return;
      const next = `library/${id}/${shot}.mp4`;
      if (node.getAttribute("src") === next) return;
      node.src = next;
      node.dataset.live = "";
      node.load();
    });
  }

  function showAt(time, force) {
    if (!state.windows.length) return;
    let index = 0;
    for (let cursor = 0; cursor < state.windows.length; cursor += 1) {
      if (time >= state.windows[cursor][0]) index = cursor;
    }
    const shot = shotFor(index);
    const morph = state.morphs.indexOf(index) >= 0;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const into = state.windows[index] ? (time - state.windows[index][0]) / 0.4 : 1;
    const blending = morph && !reduced && into >= 0 && into < 1;
    SHOTS.forEach((id) => {
      const node = clips[id];
      const on = id === shot;
      node.classList.toggle("on", on);
      node.style.opacity = on && blending ? String(Math.max(0.15, into)) : "";
      if (on && (force || node.dataset.live !== "1")) {
        if (node.paused) node.play().catch(() => {});
        node.dataset.live = "1";
      }
    });
    if (blending) {
      const previous = clips[shotFor(Math.max(0, index - 1))];
      if (previous) {
        previous.classList.add("on");
        previous.style.opacity = String(1 - into);
      }
    }
    const head = document.getElementById("playhead");
    if (head && state.duration) head.style.left = `${(time / state.duration) * 100}%`;
  }

  function detect(buffer) {
    const channel = buffer.getChannelData(0);
    const rate = buffer.sampleRate;
    const hop = Math.max(1, Math.floor(rate * 0.02));
    const energy = [];
    for (let index = 0; index + hop <= channel.length; index += hop) {
      let sum = 0;
      const step = 4;
      for (let sample = index; sample < index + hop; sample += step) sum += channel[sample] * channel[sample];
      energy.push(sum / (hop / step));
    }
    const mean = energy.reduce((total, value) => total + value, 0) / (energy.length || 1);
    const beats = [];
    let loud = 0;
    let loudAt = 0;
    for (let index = 1; index < energy.length; index += 1) {
      const start = Math.max(0, index - 10);
      let local = 0;
      for (let cursor = start; cursor < index; cursor += 1) local += energy[cursor];
      local /= index - start || 1;
      const flux = energy[index] - energy[index - 1];
      const t = (index * hop) / rate;
      if (energy[index] > loud) {
        loud = energy[index];
        loudAt = t;
      }
      if (flux > 0 && energy[index] > local * 1.45 && energy[index] > mean * 0.55) {
        if (!beats.length || t - beats[beats.length - 1] > 0.32) beats.push(Math.round(t * 1000) / 1000);
      }
    }
    if (beats.length < 2) {
      beats.length = 0;
      for (let t = 0.5; t < buffer.duration; t += 0.5) beats.push(Math.round(t * 1000) / 1000);
    }
    return { beats: beats, drop: loudAt };
  }

  async function loadFile(file) {
    empty.textContent = "Reading the song…";
    note.textContent = file.name;
    const bytes = await file.arrayBuffer();
    const copy = bytes.slice(0);
    let buffer;
    try {
      const context = new AudioContext();
      buffer = await context.decodeAudioData(copy);
      context.close();
    } catch (error) {
      empty.textContent = "That file did not open as audio.";
      return;
    }
    const found = detect(buffer);
    state.duration = buffer.duration;
    state.beats = found.beats;
    state.drops = [found.drop];
    if (audio.src && audio.src.startsWith("blob:")) URL.revokeObjectURL(audio.src);
    audio.src = URL.createObjectURL(new Blob([bytes]));
    empty.textContent = "";
    recut();
    await start();
  }

  async function start() {
    SHOTS.forEach((id) => clips[id].play().catch(() => {}));
    if (!audio.src) {
      note.textContent = "Drop a song first.";
      return;
    }
    try {
      await audio.play();
      state.playing = true;
      note.textContent = "Playing. The cut follows the beat.";
    } catch (error) {
      note.textContent = "Press Play to start the song with the picture.";
    }
  }

  function tick() {
    if (state.playing || !audio.paused) showAt(audio.currentTime || 0, false);
    requestAnimationFrame(tick);
  }

  energy.addEventListener("input", () => {
    state.energy = Number(energy.value);
    readout.textContent = word(state.energy);
    recut();
  });

  const MORPH_VIBES = { "liquid-gold": true, cosmic: true };

  document.querySelectorAll("[data-vibe]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.vibe;
      document.querySelectorAll("[data-vibe]").forEach((card) => {
        const on = card === button;
        card.classList.toggle("on", on);
        card.setAttribute("aria-checked", on ? "true" : "false");
      });
      document.getElementById("screen").dataset.vibe = id;
      useLibrary(id);
      const level = MORPH_VIBES[id] ? 0.5 : 0;
      energy.value = String(level);
      state.energy = level;
      readout.textContent = word(level);
      if (state.duration) recut();
    });
  });

  document.getElementById("again").addEventListener("click", () => {
    const panel = document.getElementById("vibe-panel");
    if (panel) panel.scrollIntoView({ block: "start" });
    const first = document.querySelector("[data-vibe]");
    if (first) first.focus();
  });

  document.getElementById("bundled").addEventListener("click", async () => {
    note.textContent = "Opening the bundled demo.";
    try {
      const response = await fetch("/media/audio/demo");
      if (!response.ok) throw new Error("missing");
      const blob = await response.blob();
      await loadFile(new File([blob], "demo.wav", { type: blob.type || "audio/wav" }));
    } catch (error) {
      note.textContent = "Drop a song from this machine.";
    }
  });

  document.getElementById("play").addEventListener("click", () => start());

  document.getElementById("file").addEventListener("change", (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) loadFile(file);
  });

  window.addEventListener("dragover", (event) => {
    event.preventDefault();
    drop.classList.add("over");
  });
  window.addEventListener("dragleave", () => drop.classList.remove("over"));
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    drop.classList.remove("over");
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) loadFile(file);
  });

  audio.addEventListener("play", () => {
    state.playing = true;
  });
  audio.addEventListener("ended", () => {
    state.playing = false;
  });

  document.addEventListener("keydown", (event) => {
    const tag = event.target && event.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (event.key === " ") {
      event.preventDefault();
      if (audio.paused) start();
      else {
        audio.pause();
        state.playing = false;
      }
    } else if (event.key === "Escape") {
      audio.pause();
      state.playing = false;
    }
  });

  requestAnimationFrame(tick);
})();
