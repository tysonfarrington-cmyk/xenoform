/* Guided tours. Steps live in tutorial.json so the copy can change without touching this file. */
(function () {
  const KEY = "xenoform.tutorial";
  const SIM = "Simulated. No GPU job was started. The bundled demo stands in.";
  let catalog = null;
  let catalogPromise = null;
  let running = null;
  let inputTimer = 0;
  let placeTries = 0;

  function read() {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) || "{}");
      return {
        offered: !!raw.offered,
        active: raw.active || "",
        progress: raw.progress || {},
        done: raw.done || {},
      };
    } catch (error) {
      return { offered: false, active: "", progress: {}, done: {} };
    }
  }

  function write(next) {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch (error) {}
  }

  function catalogReady() {
    if (catalog) return Promise.resolve(catalog);
    if (!catalogPromise) {
      catalogPromise = fetch("/static/tutorial.json")
        .then((response) => response.json())
        .then((data) => {
          catalog = data;
          return data;
        })
        .catch(() => {
          catalogPromise = null;
          return null;
        });
    }
    return catalogPromise;
  }

  function tourById(id) {
    if (!catalog) return null;
    return (catalog.tours || []).find((tour) => tour.id === id) || null;
  }

  function currentTour() {
    return running ? tourById(running.tour) : null;
  }

  function currentStep() {
    const tour = currentTour();
    if (!tour) return null;
    const id = tour.steps[running.index];
    if (!id || !catalog.steps) return null;
    return catalog.steps[id] || null;
  }

  function viewName() {
    const hash = (location.hash || "#simple").replace("#", "").split("/")[0] || "simple";
    return hash === "scene" ? "director" : hash;
  }

  function reduceMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function narrow() {
    return window.innerWidth <= 720;
  }

  function ensureRoot() {
    let root = document.getElementById("tutorial-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "tutorial-root";
    root.innerHTML = `
      <div id="tutorial-offer" class="tour-offer" role="dialog" aria-modal="false" aria-labelledby="tutorial-offer-title" hidden>
        <p class="kicker">Tyso Studio</p>
        <h2 id="tutorial-offer-title">Simple mode in 30 seconds</h2>
        <p id="tutorial-offer-copy">Song, a vibe, then Make. You can leave and come back, or skip it.</p>
        <div class="tour-actions">
          <button type="button" class="ghost" id="tutorial-later">Not now</button>
          <button type="button" class="generate" id="tutorial-start">Start</button>
        </div>
      </div>
      <div id="tutorial-shade" hidden>
        <div class="tour-dim" data-edge="top"></div>
        <div class="tour-dim" data-edge="left"></div>
        <div class="tour-dim" data-edge="right"></div>
        <div class="tour-dim" data-edge="bottom"></div>
        <div class="tour-ring" hidden></div>
      </div>
      <div id="tutorial-card" class="tour-card" role="dialog" aria-modal="false" aria-labelledby="tour-title" aria-live="polite" hidden>
        <p class="tour-kicker" id="tour-kicker"></p>
        <h2 id="tour-title"></h2>
        <div id="tour-body"></div>
        <p class="tour-sim" id="tour-sim" hidden></p>
        <p class="tour-count" id="tour-count"></p>
        <div class="tour-actions">
          <button type="button" class="ghost" id="tour-back">Back</button>
          <button type="button" class="text" id="tour-skip">Skip</button>
          <button type="button" class="generate" id="tour-next">Next</button>
        </div>
      </div>`;
    document.body.appendChild(root);
    document.getElementById("tutorial-start").addEventListener("click", () => {
      dismissOffer(true);
      const simple = document.body.dataset.advanced !== "1";
      begin(simple ? "simple" : "first-video", { resume: false });
    });
    document.getElementById("tutorial-later").addEventListener("click", () => dismissOffer(true));
    document.getElementById("tour-back").addEventListener("click", back);
    document.getElementById("tour-skip").addEventListener("click", skip);
    document.getElementById("tour-next").addEventListener("click", next);
    return root;
  }

  function dismissOffer(mark) {
    const offer = document.getElementById("tutorial-offer");
    if (offer) offer.hidden = true;
    if (mark) {
      const saved = read();
      saved.offered = true;
      write(saved);
    }
  }

  function showOffer() {
    ensureRoot();
    const offer = document.getElementById("tutorial-offer");
    offer.hidden = false;
    const simple = document.body.dataset.advanced !== "1";
    const title = document.getElementById("tutorial-offer-title");
    const copy = document.getElementById("tutorial-offer-copy");
    if (title) title.textContent = simple ? "Simple mode in 30 seconds" : "Walk the desk";
    if (copy) {
      copy.textContent = simple
        ? "Song, a vibe, then Make. You can leave and come back, or skip it."
        : "A short tour, one control at a time. You can leave and come back, or skip it.";
    }
    const start = document.getElementById("tutorial-start");
    if (start) start.focus();
  }

  function updateButton() {
    const button = document.getElementById("tutorial-open");
    if (!button) return;
    const saved = read();
    const id = saved.active || "";
    const mid = id && !saved.done[id] && Number(saved.progress[id] || 0) > 0 && !running;
    button.textContent = mid ? "Resume" : "Tutorial";
    button.setAttribute("aria-expanded", running ? "true" : "false");
  }

  function paintTours() {
    const list = document.getElementById("tour-list");
    if (!list || !catalog) return;
    const saved = read();
    list.replaceChildren();
    (catalog.tours || []).forEach((tour) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.tourId = tour.id;
      const progress = Number(saved.progress[tour.id] || 0);
      const done = !!saved.done[tour.id];
      const label = !done && progress > 0 ? "Resume" : "Start";
      const strong = document.createElement("strong");
      strong.textContent = tour.name;
      const span = document.createElement("span");
      span.textContent = tour.blurb || "";
      const em = document.createElement("em");
      em.textContent = label;
      button.append(strong, span, em);
      list.appendChild(button);
    });
  }

  function hide() {
    const was = running;
    running = null;
    clearTimeout(inputTimer);
    document.body.dataset.tour = "0";
    const shade = document.getElementById("tutorial-shade");
    const card = document.getElementById("tutorial-card");
    if (shade) shade.hidden = true;
    if (card) card.hidden = true;
    updateButton();
    if (was) document.dispatchEvent(new CustomEvent("xeno-tour-end"));
  }

  function begin(id, options) {
    catalogReady().then(() => {
      const tour = tourById(id);
      if (!tour) return;
      ensureRoot();
      dismissOffer(true);
      const saved = read();
      const resume = options && options.resume;
      let index = resume ? Number(saved.progress[id] || 0) : 0;
      if (saved.done[id] && resume) index = 0;
      if (index >= tour.steps.length) index = 0;
      saved.active = id;
      saved.offered = true;
      saved.progress[id] = index;
      if (resume && saved.done[id]) saved.done[id] = false;
      write(saved);
      running = { tour: id, index };
      document.body.dataset.tour = "1";
      apply();
    });
  }

  function persistIndex() {
    if (!running) return;
    const saved = read();
    saved.active = running.tour;
    saved.progress[running.tour] = running.index;
    saved.offered = true;
    write(saved);
  }

  function next() {
    const tour = currentTour();
    if (!tour) return;
    clearTimeout(inputTimer);
    if (running.index >= tour.steps.length - 1) {
      const saved = read();
      saved.done[running.tour] = true;
      saved.progress[running.tour] = 0;
      saved.active = running.tour;
      write(saved);
      hide();
      paintTours();
      return;
    }
    running.index += 1;
    persistIndex();
    apply();
  }

  function back() {
    if (!running || running.index <= 0) return;
    clearTimeout(inputTimer);
    running.index -= 1;
    persistIndex();
    apply();
  }

  function skip() {
    persistIndex();
    hide();
    paintTours();
  }

  function contextReady(step) {
    if (!step) return true;
    if ((step.view || "simple") !== viewName()) return false;
    if (step.quality) {
      const on = document.querySelector(`button.on[data-act="quality"][data-quality="${step.quality}"]`);
      if (!on) return false;
    }
    return true;
  }

  function armContext(step) {
    const want = step.view || "simple";
    if (viewName() !== want) {
      location.hash = want;
      return;
    }
    if (step.quality) {
      const button = document.querySelector(`[data-act="quality"][data-quality="${step.quality}"]`);
      if (button) button.click();
    }
  }

  function fillCard(step) {
    const tour = currentTour();
    const card = document.getElementById("tutorial-card");
    card.hidden = false;
    document.getElementById("tour-kicker").textContent = tour ? tour.name : "Tutorial";
    const title = document.getElementById("tour-title");
    title.textContent = step.title || "";
    const body = document.getElementById("tour-body");
    body.replaceChildren();
    (step.body || []).forEach((line) => {
      const p = document.createElement("p");
      p.textContent = line;
      body.appendChild(p);
    });
    if (step.badge) {
      const badge = document.createElement("p");
      const span = document.createElement("a");
      span.className = "ow-badge";
      span.href = (window.XENO_BASE || "") + "/licences";
      span.title = "LTX-2.3 has a revenue threshold. FLUX.2 Klein 9B is non-commercial. This desk uses the Apache 2.0 4B.";
      span.textContent = "Open weights";
      badge.appendChild(span);
      body.appendChild(badge);
    }
    const sim = document.getElementById("tour-sim");
    if (step.sim) {
      sim.hidden = false;
      sim.textContent = step.sim || SIM;
    } else {
      sim.hidden = true;
      sim.textContent = "";
    }
    const total = tour ? tour.steps.length : 1;
    document.getElementById("tour-count").textContent = `Step ${running.index + 1} of ${total}`;
    const last = tour && running.index >= tour.steps.length - 1;
    document.getElementById("tour-next").textContent = last ? "Done" : "Next";
    document.getElementById("tour-back").disabled = running.index <= 0;
  }

  function edge(name) {
    return document.querySelector(`#tutorial-shade .tour-dim[data-edge="${name}"]`);
  }

  function layout(node) {
    const shade = document.getElementById("tutorial-shade");
    const ring = shade.querySelector(".tour-ring");
    const card = document.getElementById("tutorial-card");
    shade.hidden = false;
    const dimTop = edge("top");
    const dimLeft = edge("left");
    const dimRight = edge("right");
    const dimBottom = edge("bottom");
    if (!node) {
      dimTop.style.cssText = "top:0;left:0;right:0;bottom:0";
      dimLeft.style.cssText = "display:none";
      dimRight.style.cssText = "display:none";
      dimBottom.style.cssText = "display:none";
      ring.hidden = true;
      card.classList.add("is-center");
      card.classList.toggle("is-sheet", narrow());
      card.style.top = "";
      card.style.left = "";
      return;
    }
    dimLeft.style.display = "";
    dimRight.style.display = "";
    dimBottom.style.display = "";
    const pad = 8;
    const rect = node.getBoundingClientRect();
    const sheetLimit = narrow() && card && !card.hidden && card.classList.contains("is-sheet")
      ? card.getBoundingClientRect().top - 8
      : window.innerHeight;
    const boxTop = Math.max(0, Math.round(rect.top - pad));
    const boxLeft = Math.max(0, Math.round(rect.left - pad));
    const boxRight = Math.min(window.innerWidth, Math.round(rect.right + pad));
    const boxBottom = Math.min(window.innerHeight, sheetLimit, Math.round(rect.bottom + pad));
    const box = {
      top: boxTop,
      left: boxLeft,
      width: Math.max(0, boxRight - boxLeft),
      height: Math.max(0, boxBottom - boxTop),
    };
    dimTop.style.cssText = `top:0;left:0;right:0;height:${box.top}px`;
    dimLeft.style.cssText = `top:${box.top}px;left:0;width:${box.left}px;height:${box.height}px`;
    dimRight.style.cssText = `top:${box.top}px;left:${box.left + box.width}px;right:0;height:${box.height}px`;
    dimBottom.style.cssText = `top:${box.top + box.height}px;left:0;right:0;bottom:0`;
    ring.hidden = false;
    ring.style.cssText = `top:${box.top}px;left:${box.left}px;width:${box.width}px;height:${box.height}px`;
    placeCard(card, rect);
  }

  function placeCard(card, rect) {
    card.classList.remove("is-center");
    if (narrow()) {
      card.classList.add("is-sheet");
      card.style.top = "";
      card.style.left = "";
      return;
    }
    card.classList.remove("is-sheet");
    const margin = 12;
    const width = card.offsetWidth || 360;
    const height = card.offsetHeight || 180;
    let top = rect.bottom + margin;
    let left = Math.min(rect.left, window.innerWidth - width - margin);
    if (top + height > window.innerHeight - margin) top = rect.top - height - margin;
    if (top < margin) top = Math.min(rect.bottom + margin, window.innerHeight - height - margin);
    if (top < margin) top = margin;
    if (left < margin) left = margin;
    card.style.top = `${top}px`;
    card.style.left = `${left}px`;
  }

  function reveal(node) {
    const header = document.querySelector(".top");
    if (header && header.contains(node)) return;
    const bar = header ? Math.ceil(header.getBoundingClientRect().bottom) + 12 : 88;
    const card = document.getElementById("tutorial-card");
    const sheet = narrow() && card && !card.hidden && card.classList.contains("is-sheet");
    const limit = sheet ? card.getBoundingClientRect().top - 12 : window.innerHeight - 24;
    const rect = node.getBoundingClientRect();
    const fullyVisible = rect.top >= bar && rect.bottom <= limit;
    if (fullyVisible && rect.height <= limit - bar) return;
    const top = window.scrollY + rect.top - bar;
    window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
  }

  function focusCard(step) {
    const active = document.activeElement;
    if (active && step && step.hit && active.matches && active.matches(step.hit)) return;
    const next = document.getElementById("tour-next");
    if (next) next.focus({ preventScroll: true });
  }

  function place(step) {
    ensureRoot();
    fillCard(step);
    const node = step.target ? document.querySelector(step.target) : null;
    if (step.target && !node) {
      if (placeTries === 0) {
        document.dispatchEvent(new CustomEvent("xeno-tour-step", { detail: { target: step.target } }));
      }
      if (placeTries < 20) {
        placeTries += 1;
        window.setTimeout(() => {
          if (running) place(currentStep() || step);
        }, 80);
      }
      layout(null);
      return;
    }
    placeTries = 0;
    if (node) reveal(node);
    layout(node);
    window.requestAnimationFrame(() => {
      if (!running) return;
      const again = step.target ? document.querySelector(step.target) : null;
      if (again) reveal(again);
      layout(again);
      focusCard(step);
    });
  }

  function apply() {
    paintTours();
    updateButton();
    if (!running) {
      hide();
      return;
    }
    const step = currentStep();
    if (!step) {
      hide();
      return;
    }
    if (!contextReady(step)) {
      armContext(step);
      return;
    }
    place(step);
  }

  function sync() {
    catalogReady().then(() => {
      paintTours();
      updateButton();
      if (running) apply();
    });
  }

  function reposition() {
    if (!running) return;
    const step = currentStep();
    if (!step) return;
    layout(step.target ? document.querySelector(step.target) : null);
  }

  function hitNode(event, step) {
    if (!step || !step.hit) return null;
    const node = event.target && event.target.closest ? event.target.closest(step.hit) : null;
    if (!node) return null;
    if (node.closest("#tutorial-root")) return null;
    return node;
  }

  function acted(event, step) {
    const node = hitNode(event, step);
    if (!node) return false;
    const kinds = step.on || [];
    if (!kinds.includes(event.type)) return false;
    if (event.type === "click" && node.matches("input, textarea, select")) return false;
    if (event.type === "click" && event.target.closest("label") && node.matches("input")) return false;
    return true;
  }

  document.addEventListener(
    "click",
    (event) => {
      if (!running) return;
      const step = currentStep();
      if (!step) return;
      if (step.simulate && event.target.closest(step.simulate)) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        next();
        return;
      }
      if (acted(event, step)) next();
    },
    true,
  );

  document.addEventListener(
    "change",
    (event) => {
      if (!running) return;
      const step = currentStep();
      if (!step || !acted(event, step)) return;
      if (step.target === "#energy") {
        window.setTimeout(() => {
          if (running && currentStep() === step) next();
        }, 800);
        return;
      }
      next();
    },
    true,
  );

  document.addEventListener(
    "input",
    (event) => {
      if (!running) return;
      const step = currentStep();
      if (!step || !acted(event, step)) return;
      clearTimeout(inputTimer);
      inputTimer = window.setTimeout(() => {
        if (running && currentStep() === step) next();
      }, 700);
    },
    true,
  );

  document.addEventListener("click", (event) => {
    const pick = event.target.closest("#tour-list [data-tour-id]");
    if (!pick) return;
    begin(pick.dataset.tourId, { resume: true });
  });

  document.addEventListener("keydown", (event) => {
    const offer = document.getElementById("tutorial-offer");
    const offerOpen = offer && !offer.hidden;
    if (document.querySelector("dialog[open]")) return;
    if (event.key === "Escape" && offerOpen && !running) {
      event.preventDefault();
      dismissOffer(true);
      return;
    }
    if (!running) return;
    if (event.key === "Escape") {
      event.preventDefault();
      skip();
      return;
    }
    const tag = document.activeElement && document.activeElement.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    if (typing) return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      next();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      back();
    }
  });

  window.addEventListener("resize", () => reposition());
  window.addEventListener(
    "scroll",
    () => {
      if (!running) return;
      window.requestAnimationFrame(() => reposition());
    },
    true,
  );

  function bindChrome() {
    const open = document.getElementById("tutorial-open");
    if (open && !open.dataset.bound) {
      open.dataset.bound = "1";
      open.addEventListener("click", () => {
        const saved = read();
        const fallback = document.body.dataset.advanced === "1" ? "first-video" : "simple";
        const id = saved.active && !saved.done[saved.active] ? saved.active : fallback;
        const mid = id && Number(saved.progress[id] || 0) > 0 && !saved.done[id];
        begin(id, { resume: !!mid });
      });
    }
    const reset = document.getElementById("reset-tutorial");
    if (reset && !reset.dataset.bound) {
      reset.dataset.bound = "1";
      reset.addEventListener("click", () => {
        write({ offered: false, active: "", progress: {}, done: {} });
        running = null;
        hide();
        paintTours();
        const settings = document.getElementById("settings");
        if (settings && settings.open) settings.close();
        showOffer();
      });
    }
  }

  window.XENO_TUTORIAL = {
    ready() {
      bindChrome();
      catalogReady().then(() => {
        paintTours();
        updateButton();
        const saved = read();
        if (!saved.offered && !running) showOffer();
      });
    },
    sync() {
      bindChrome();
      sync();
    },
    reposition,
    reset() {
      const button = document.getElementById("reset-tutorial");
      if (button) button.click();
    },
  };

  if (document.readyState !== "loading") bindChrome();
  else document.addEventListener("DOMContentLoaded", bindChrome);
})();
