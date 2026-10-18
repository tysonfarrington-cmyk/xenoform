/* Prompt chips. Categories and lines live in ideas.json. */
(function () {
  const BIND = [
    { sel: "#brief", field: "brief", tour: true },
    { sel: "#easy-idea", field: "brief" },
    { sel: "textarea[data-prompt]", field: "shot" },
    { sel: "textarea[data-scene='action']", field: "shot" },
    { sel: "[data-scene='verb']", field: "shot" },
    { sel: "[data-scene='goal']", field: "brief" },
    { sel: "[data-scene='payoff']", field: "brief" },
    { sel: "#callback", field: "brief" },
    { sel: "#style-note", field: "style" },
    { sel: "#transition-note", field: "transition" },
    { sel: "#title-card, #end-card", field: "style" },
    { sel: "#noun", field: "style" },
  ];
  const SHOW = 4;
  let catalog = null;
  let catalogPromise = null;
  const memory = {};
  let shiftHeld = false;

  function catalogReady() {
    if (catalog) return Promise.resolve(catalog);
    if (!catalogPromise) {
      catalogPromise = fetch("/static/ideas.json")
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

  function fieldOf(name) {
    return catalog && catalog.fields && catalog.fields[name];
  }

  function keyFor(input) {
    if (input.id) return input.id;
    if (input.dataset.prompt != null) return "prompt-" + input.dataset.prompt;
    if (input.dataset.scene) return input.dataset.scene + "-" + (input.dataset.index || "0");
    if (input.dataset.card) return "card-" + input.dataset.card;
    return input.getAttribute("aria-label") || "field";
  }

  function slotFor(input, field) {
    const key = keyFor(input);
    if (!memory[key]) memory[key] = { field: field, category: 0, salt: 0 };
    memory[key].field = field;
    return memory[key];
  }

  function categories(field) {
    const body = fieldOf(field);
    return (body && body.categories) || [];
  }

  function plainIdeas(input) {
    return !!(input && input.id === "easy-idea");
  }

  function showCount(input) {
    if (plainIdeas(input)) return 2;
    return window.matchMedia("(max-width: 720px)").matches ? 2 : SHOW;
  }

  function visible(ideas, salt, input) {
    if (!ideas.length) return [];
    const count = Math.min(showCount(input), ideas.length);
    const start = ((salt % ideas.length) + ideas.length) % ideas.length;
    const out = [];
    for (let i = 0; i < count; i += 1) out.push(ideas[(start + i) % ideas.length]);
    return out;
  }

  function clip(text, max) {
    if (!max || text.length <= max) return text;
    const cut = text.slice(0, max);
    const space = cut.lastIndexOf(" ");
    return (space > 20 ? cut.slice(0, space) : cut).replace(/[\s,;:.]+$/, "");
  }

  function nextValue(current, idea, replace, max) {
    const clean = String(idea || "").trim();
    if (replace || !String(current || "").trim()) return clip(clean, max);
    const joined = String(current).replace(/\s+$/, "") + " " + clean;
    if (max && joined.length > max) return clip(clean, max);
    return joined;
  }

  function applyTo(input, idea, replace) {
    if (!input || input.disabled) return;
    const max = Number(input.getAttribute("maxlength")) || 0;
    input.value = nextValue(input.value, idea, replace, max);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function dieIcon() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "14");
    svg.setAttribute("height", "14");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    const rect = document.createElementNS(svg.namespaceURI, "rect");
    rect.setAttribute("x", "1");
    rect.setAttribute("y", "1");
    rect.setAttribute("width", "14");
    rect.setAttribute("height", "14");
    rect.setAttribute("fill", "none");
    rect.setAttribute("stroke", "currentColor");
    rect.setAttribute("stroke-width", "1.4");
    svg.appendChild(rect);
    [[5, 5], [11, 5], [8, 8], [5, 11], [11, 11]].forEach(([cx, cy]) => {
      const dot = document.createElementNS(svg.namespaceURI, "circle");
      dot.setAttribute("cx", String(cx));
      dot.setAttribute("cy", String(cy));
      dot.setAttribute("r", "1");
      dot.setAttribute("fill", "currentColor");
      svg.appendChild(dot);
    });
    return svg;
  }

  function paint(row, input, field) {
    const cats = categories(field);
    if (!cats.length) return;
    const slot = slotFor(input, field);
    slot.category = ((slot.category % cats.length) + cats.length) % cats.length;
    const cat = cats[slot.category];
    const ideas = visible(cat.ideas || [], slot.salt, input);
    const plain = plainIdeas(input);
    row.replaceChildren();
    const meta = document.createElement("div");
    meta.className = "idea-meta";
    const label = document.createElement("span");
    label.className = "idea-cat";
    label.id = row.dataset.rowId + "-cat";
    label.textContent = cat.name || "Ideas";
    const shuffle = document.createElement("button");
    shuffle.type = "button";
    shuffle.className = "ghost idea-shuffle";
    shuffle.dataset.act = "idea-shuffle";
    shuffle.setAttribute("aria-label", "Shuffle ideas");
    shuffle.textContent = "Shuffle";
    const dice = document.createElement("button");
    dice.type = "button";
    dice.className = "ghost idea-dice";
    dice.dataset.act = "idea-dice";
    dice.setAttribute("aria-label", "Fill one random idea");
    dice.append(dieIcon(), document.createTextNode(" Dice"));
    const hint = document.createElement("span");
    hint.className = "idea-hint";
    hint.textContent = "Shift replaces";
    if (plain) meta.append(dice);
    else meta.append(label, shuffle, dice, hint);
    const chips = document.createElement("div");
    chips.className = "idea-chips";
    chips.setAttribute("role", "group");
    if (plain) chips.setAttribute("aria-label", "Ideas");
    else chips.setAttribute("aria-labelledby", label.id);
    ideas.forEach((idea) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "idea-chip";
      button.dataset.act = "idea-use";
      button.dataset.idea = idea;
      button.textContent = idea;
      button.title = plain ? idea : idea + " — add this idea. Hold Shift to replace the text.";
      chips.appendChild(button);
    });
    row.append(meta, chips);
  }

  function attach(input, field, tour) {
    if (!input || input.dataset.ideasBound === "1") return;
    const cats = categories(field);
    if (!cats.length) return;
    input.dataset.ideasBound = "1";
    const row = document.createElement("div");
    row.className = "idea-row";
    row.dataset.ideasFor = keyFor(input);
    row.dataset.rowId = "idea-" + keyFor(input).replace(/[^a-z0-9_-]+/gi, "-");
    if (tour) row.dataset.tour = "ideas";
    const anchor = input.parentElement && input.parentElement.tagName === "LABEL" ? input.parentElement : input;
    anchor.insertAdjacentElement("afterend", row);
    paint(row, input, field);
  }

  function mount() {
    catalogReady().then(() => {
      if (!catalog) return;
      document.querySelectorAll("[data-ideas-bound]").forEach((input) => {
        delete input.dataset.ideasBound;
      });
      document.querySelectorAll(".idea-row").forEach((row) => row.remove());
      BIND.forEach((binding) => {
        document.querySelectorAll(binding.sel).forEach((input) => attach(input, binding.field, binding.tour));
      });
    });
  }

  function rowInput(row) {
    const key = row && row.dataset.ideasFor;
    if (!key) return null;
    return BIND.reduce((found, binding) => {
      if (found) return found;
      return [...document.querySelectorAll(binding.sel)].find((input) => keyFor(input) === key) || null;
    }, null);
  }

  function fieldName(input) {
    const hit = BIND.find((binding) => input.matches(binding.sel));
    return hit ? hit.field : "";
  }

  document.addEventListener("click", (event) => {
    const shuffle = event.target.closest("[data-act=idea-shuffle]");
    const dice = event.target.closest("[data-act=idea-dice]");
    const chip = event.target.closest("[data-act=idea-use]");
    const row = event.target.closest(".idea-row");
    if (!row) return;
    const input = rowInput(row);
    if (!input) return;
    const field = fieldName(input);
    const replace = event.shiftKey || shiftHeld;
    if (shuffle) {
      const slot = slotFor(input, field);
      const total = categories(field).length || 1;
      slot.category = (slot.category + 1) % total;
      slot.salt = Math.floor(Math.random() * 10);
      paint(row, input, field);
      const next = row.querySelector("[data-act=idea-shuffle]");
      if (next) next.focus();
      return;
    }
    if (dice) {
      const all = categories(field).flatMap((cat) => cat.ideas || []);
      if (!all.length) return;
      applyTo(input, all[Math.floor(Math.random() * all.length)], replace);
      return;
    }
    if (chip) applyTo(input, chip.dataset.idea || chip.textContent, replace);
  });

  window.addEventListener("resize", () => {
    if (!catalog) return;
    document.querySelectorAll(".idea-row").forEach((row) => {
      const input = rowInput(row);
      if (!input) return;
      paint(row, input, fieldName(input));
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Shift") shiftHeld = true;
  });
  document.addEventListener("keyup", (event) => {
    if (event.key === "Shift") shiftHeld = false;
  });

  window.XENO_IDEAS = { mount };
})();
