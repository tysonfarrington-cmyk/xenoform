// The MIDI layer under node (no browser): `node tests/js/midi_test.js`, or tests/test_midi_js.py in the suite.
// midi.js loads two ways: require() gives its pure core (profiles, resolve, the hold stack, soft takeover, the maps
// by device name), and run in a vm sandbox with a stub window it gives the runtime (window.XenoMidi), so handle() is
// tested as a page uses it: events in, handlers and holds out.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FILE = path.join(__dirname, "..", "..", "src", "xenoform", "ui_static", "midi.js");
const C = require(FILE);
const note = (num, value, extra) => Object.assign({ type: "note", ch: 10, num, value, t: 0 }, extra || {});
const cc = (num, value, extra) => Object.assign({ type: "cc", ch: 1, num, value, t: 0 }, extra || {});

// ---------------------------------------------------------------- the runtime in a sandbox
function runtime(store) {
  const data = Object.assign({}, store || {});
  const localStorage = { getItem: k => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); }, removeItem: k => { delete data[k]; } };
  const noop = () => {};
  const document = { addEventListener: noop, body: { classList: { toggle: noop } }, querySelector: () => null, head: { appendChild: noop } };
  const sandbox = { localStorage, document, navigator: {}, location: { search: "?webmidi=0", protocol: "http:", host: "127.0.0.1" },
    console, setTimeout, clearTimeout, Date, JSON, Math, Object, Array, Promise, RegExp, String, Number, isFinite };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(FILE, "utf8"), sandbox, { filename: "midi.js" });
  return { X: sandbox.XenoMidi, data };
}
function page(opts, store) {
  const { X, data } = runtime(store);
  const fired = [], held = [];
  X.init(Object.assign({ page: "vj", bridge: false, targets: { "*": (t, v) => fired.push([t, +(+v).toFixed(3)]) },
    onHold: (id, on, info) => held.push([id, on, info.top]) }, opts || {}));
  return { X, data, fired, held };
}

// ---------------------------------------------------------------- the hold stack
test("holds: last in wins, a release anywhere in the stack keeps the top, clear lets go of all", () => {
  const h = new C.HoldStack(), seen = [];
  const off = h.on((id, on, top) => seen.push(`${id}${on ? "+" : "-"}>${top}`));
  h.press("pad:1"); h.press("pad:2"); h.press("strobe");
  assert.equal(h.top(), "strobe");
  assert.equal(h.top("pad:"), "pad:2");            // the top one of a family
  h.release("pad:1");                              // an older pad lets go: what shows does not change
  assert.equal(h.top("pad:"), "pad:2");
  h.press("pad:2");                                // pressed again: back on top, never twice in the stack
  assert.deepEqual(h.list(), ["strobe", "pad:2"]);
  assert.equal(h.release("pad:9"), false);         // not held: nothing to tell
  h.clear();
  assert.deepEqual(h.list(), []);
  assert.deepEqual(seen, ["pad:1+>pad:1", "pad:2+>pad:2", "strobe+>strobe", "pad:1->strobe", "pad:2+>pad:2", "pad:2->strobe", "strobe->null"]);
  off(); h.press("pad:3");
  assert.equal(seen.length, 7);                    // unsubscribed
});

test("resolve: a hold row presses on note-on or a CC button down, releases on note-off or below 64", () => {
  const row = { source: { type: "note", ch: 10, num: 36 }, target: "pad:1", mode: "hold", min: 0, max: 1 }, st = {};
  assert.deepEqual(C.resolve(row, note(36, 100), st), { target: "pad:1", value: 1, kind: "press" });
  assert.deepEqual(C.resolve(row, note(36, 0), st), { target: "pad:1", value: 0, kind: "release" });
  const btn = { source: { type: "cc", ch: 1, num: 20 }, target: "pad:2", mode: "hold", min: 0, max: 1 };
  assert.equal(C.resolve(btn, cc(20, 127), st).kind, "press");
  assert.equal(C.resolve(btn, cc(20, 63), st).kind, "release");
  // the other modes, for the record
  const tog = { source: { type: "note", num: 50 }, target: "strobe", mode: "toggle", min: 0, max: 1 };
  assert.equal(C.resolve(tog, note(50, 90), st).value, 1);
  assert.equal(C.resolve(tog, note(50, 0), st), null);
  assert.equal(C.resolve(tog, note(50, 90), st).value, 0);
  const tap = { source: { type: "cc", ch: 1, num: 21 }, target: "tap", mode: C.modeFor("tap", "cc"), min: 0, max: 1 };
  assert.equal(tap.mode, "trigger");
  const presses = [10, 70, 90, 30, 127, 127, 0].map(v => !!C.resolve(tap, cc(21, v), st));
  assert.deepEqual(presses, [false, true, false, false, true, true, false]);  // up through 64, or a 127-only button again
  const knob = { source: { type: "cc", ch: 1, num: 74 }, target: "intensity", mode: "abs", min: 0, max: 2 };
  assert.equal(C.resolve(knob, cc(74, 127), st).value, 2);
  const enc = { source: { type: "cc", ch: 1, num: 28 }, target: "every", mode: "rel", min: 0, max: 1 }, es = { every: 0.5 };
  assert.equal(C.resolve(enc, cc(28, 70), es).value, 0.56);
  assert.equal(C.resolve(enc, cc(28, 1), es).value, 0);  // clamped at the bottom
});

// ---------------------------------------------------------------- soft takeover
test("takeover: a knob away from the value waits, takes over within reach or once it passes the value", () => {
  const tk = new C.Takeover();
  assert.deepEqual(tk.decide("k", 0.9, null, 0, 1), { apply: true, picked: true, dir: 0 });  // nothing on screen to catch
  assert.deepEqual(tk.decide("a", 1.0, 0.5, 0, 1), { apply: false, picked: false, dir: -1 }); // far above: turn it down
  assert.deepEqual(tk.away("a"), { hw: 1.0, screen: 0.5, dir: -1 });
  assert.equal(tk.decide("a", 0.6, 0.5, 0, 1).apply, false);
  assert.equal(tk.decide("a", 0.52, 0.5, 0, 1).apply, true);        // within 3 %: takes over
  assert.equal(tk.away("a"), null);
  assert.equal(tk.decide("a", 0.9, 0.52, 0, 1).apply, true);        // follows from then on
  assert.equal(tk.decide("a", 0.95, 0.3, 0, 1).apply, false);       // the value moved on screen (a reset): wait again
  assert.equal(tk.decide("a", 0.1, 0.3, 0, 1).apply, true);         // ...until the knob passes it, in one jump or not
  assert.equal(tk.decide("b", 0.0, 1.0, 0, 2).apply, false);        // the window is 3 % of the range (0..2 here)
  assert.equal(tk.decide("b", 0.95, 1.0, 0, 2).apply, true);
  tk.reset("a"); assert.equal(tk.away("a"), null);
});

// ---------------------------------------------------------------- profiles and maps by device name
test("the port's name picks the map: a shipped preset, the MiniLab 3 by name, else the generic map", () => {
  assert.equal(C.pickDefault("Minilab3").id, "minilab3");           // Windows' name for it
  assert.equal(C.pickDefault("Minilab3 MIDI").id, "minilab3");      // macOS
  assert.equal(C.pickDefault("Arturia MiniLab 3 0").id, "minilab3");
  assert.equal(C.pickDefault("MIDIIN2 (Minilab3)").id, "minilab3"); // its side port too
  assert.equal(C.pickDefault("nanoKONTROL2").id, "generic");
  assert.equal(C.pickDefault("").id, "minilab3");                   // no name (an old bridge, a script): as before
  const presets = [{ id: "bad", match: "(", device: "Launchpad X", pages: { vj: [] } },
                   { id: "tys", match: "mini\\s*lab\\s*3", label: "Tys's MiniLab 3", profile: "minilab3", pages: { vj: [{ source: { type: "note", ch: 10, num: 36 }, target: "fx:1", mode: "trigger" }] } }];
  const tys = C.pickDefault("Minilab3", presets);
  assert.equal(tys.kind, "preset"); assert.equal(tys.label, "Tys's MiniLab 3");
  assert.equal(C.defaultRows(tys, "vj")[0].target, "fx:1");
  assert.equal(C.defaultRows(tys, "desk")[0].target, "macro:intensity");  // a page the preset leaves out: its profile's
  assert.equal(C.pickDefault("Launchpad X", presets).id, "bad");          // a broken regex still matches by device name
  assert.equal(C.pickDefault("Something else", presets).id, "generic");
  assert.ok(C.sameDevice("Minilab3", "Minilab3 0") && !C.sameDevice("Minilab3", "MIDIIN2 (Minilab3)"));
  assert.equal(C.bare("MIDIIN3 (Minilab3) 2"), "MIDIIN3 (Minilab3)");
  assert.equal(C.primaryDevice(["MIDIIN2 (Minilab3)", "Minilab3", "nanoKONTROL2"]), "Minilab3");
  assert.equal(C.primaryDevice(["nanoKONTROL2", "MIDIIN2 (Minilab3)"]), "nanoKONTROL2");
});

test("the default maps: MiniLab pads A hold scenes, the generic map in CC and note order", () => {
  const vj = C.profileMapping("minilab3", "vj"), by = n => vj.find(r => r.source.type === "note" && r.source.num === n);
  assert.deepEqual([by(36).target, by(36).mode, by(43).target], ["pad:1", "hold", "pad:8"]);
  assert.deepEqual([by(44).target, by(44).mode, by(50).target, by(50).mode], ["dance:1", "trigger", "strobe", "toggle"]);
  const desk = C.profileMapping("generic", "desk").map(r => r.source.num + ">" + r.target);
  assert.deepEqual(desk, ["1>macro:intensity", "2>macro:speed", "3>macro:chaos", "4>macro:glow", "5>stem:1", "6>stem:2", "7>stem:3", "8>stem:4",
                          "9>drums", "10>bass", "11>other", "12>vocals"]);
  assert.equal(C.profileMapping("generic", "vj").find(r => r.source.num === 36 && r.source.type === "note").target, "pad:1");
  assert.equal(C.shortName("minilab3", { type: "cc", ch: 1, num: 74 }), "K1");
  assert.equal(C.shortName("minilab3", { type: "note", ch: 10, num: 46 }), "B3");
  assert.equal(C.shortName("minilab3", { type: "cc", ch: 1, num: 21 }), "CC21");
  assert.equal(C.targetName("macro:intensity"), "Intensity");
  assert.equal(C.targetName("fx:3"), "Transition 3 · Flow carry");
  assert.equal(C.targetName("stem:Kick"), "Kick stem");
  // the first midi.js's table: an untouched copy of its factory map is not the user's work, an edited one is
  const old = C.legacyFactory("minilab3", "vj");
  assert.equal(old.find(r => r.source.num === 36 && r.source.type === "note").target, "fx:1");
  assert.equal(C.isOwnLegacy(old, "minilab3", "vj"), false);
  assert.equal(C.isOwnLegacy(C.profileMapping("minilab3", "vj"), "minilab3", "vj"), false);
  assert.equal(C.isOwnLegacy(old.map(r => r.source.num === 36 ? Object.assign({}, r, { target: "mirror" }) : r), "minilab3", "vj"), true);
});

// ---------------------------------------------------------------- the runtime: events in, handlers and holds out
test("runtime: pads hold and let go over the song, last in wins, a release after a remap still lets go", () => {
  const { X, fired, held } = page();
  X._setDevices([{ name: "Minilab3", via: "Web MIDI" }], "webmidi");  // Web MIDI lists the inputs before any message
  assert.equal(X.device, "Minilab3");
  X.handle(note(36, 100), "bridge"); X.handle(note(37, 90), "bridge");
  assert.equal(X.holds.top("pad:"), "pad:2");
  X.handle(note(37, 0), "bridge");
  assert.equal(X.holds.top("pad:"), "pad:1");                       // back to the pad still down
  X.setRow({ type: "note", ch: 10, num: 36 }, "fx:1");              // the map changes while pad 1 is down...
  X.handle(note(36, 0), "bridge");
  assert.deepEqual(Array.from(X.holds.list()), []);                             // ...and its release still lets go
  assert.deepEqual(held.map(h => `${h[0]} ${h[1]} ${h[2]}`), ["pad:1 true pad:1", "pad:2 true pad:2", "pad:2 false pad:1", "pad:1 false null"]);
  assert.deepEqual(fired.filter(f => f[0].startsWith("pad:")), [["pad:1", 1], ["pad:2", 1], ["pad:2", 0], ["pad:1", 0]]);
  X.handle(note(36, 100, { dev: "Minilab3" }), "webmidi");          // now fx:1 (a trigger), not a hold
  assert.deepEqual(Array.from(X.holds.list()), []);
  // a controller unplugged mid-hold lets go of its pads
  X.handle(note(38, 100, { dev: "Minilab3" }), "webmidi");
  assert.equal(X.holds.top(), "pad:3");
  X._gone(["nanoKONTROL2"]);
  assert.deepEqual(Array.from(X.holds.list()), []);
  // a pad held through the bridge is not Web MIDI's to let go when Web MIDI's inputs change
  X.handle(note(39, 100, { dev: "Minilab3 0" }), "bridge");
  X._gone([]);
  assert.equal(X.holds.top(), "pad:4");
  X.handle(note(39, 0, { dev: "Minilab3 0" }), "bridge");
  assert.deepEqual(Array.from(X.holds.list()), []);
});

test("runtime: soft takeover holds a knob back until it reaches the value the page shows", () => {
  const screen = { intensity: 1.0 };
  const { X, fired } = page({ read: t => (t in screen ? screen[t] : null) });
  X.handle(cc(74, 0), "bridge"); X.handle(cc(74, 30), "bridge");
  assert.deepEqual(fired, []);                                       // the knob is at 0..0.47, the screen at 1.0
  const row = X.mappings.find(r => r.source.num === 74);
  assert.equal(X.away(row).dir, 1);                                  // turn it up
  X.handle(cc(74, 64), "bridge");                                    // 1.008: within reach
  assert.deepEqual(fired, [["intensity", 1.008]]);
  screen.intensity = 1.008; X.handle(cc(74, 100), "bridge");
  assert.deepEqual(fired.at(-1), ["intensity", 1.575]);
  X.handle(cc(71, 127), "bridge");                                   // the switch rate has no value on screen: at once
  assert.deepEqual(fired.at(-1), ["every", 1]);
});

test("runtime: each controller plays its own map, the device picks it, maps persist and reset", () => {
  const { X, fired, data } = page();
  X._setDevices([{ name: "MIDIIN2 (Minilab3)", via: "Web MIDI" }, { name: "Minilab3", via: "Web MIDI" }, { name: "nanoKONTROL2", via: "Web MIDI" }], "webmidi");
  assert.equal(X.device, "Minilab3");                               // the main port of a known controller
  assert.equal(X.choice.id, "minilab3");
  X.handle(note(36, 100, { dev: "nanoKONTROL2" }), "webmidi");      // the nano's notes 36.. are the generic pads
  assert.equal(X.holds.top(), "pad:1");
  X.handle(note(36, 0, { dev: "nanoKONTROL2" }), "webmidi");
  X.handle(cc(1, 127, { dev: "nanoKONTROL2" }), "webmidi");         // generic CC 1 = intensity
  assert.deepEqual(fired.at(-1), ["intensity", 2]);
  // learn on the MiniLab: its own map, saved under its name, the nano's untouched
  X.learn("mirror"); X.handle(note(37, 99, { dev: "Minilab3" }), "webmidi");
  assert.equal(X.rowOf({ type: "note", ch: 10, num: 37 }).target, "mirror");
  const st = JSON.parse(data["xeno-midi"]);
  assert.equal(st.version, 2); assert.equal(st.active, "Minilab3");
  assert.equal(st.devices.Minilab3.pages.vj.find(r => r.source.num === 37).target, "mirror");
  assert.equal(X.rowsFor("nanoKONTROL2").find(r => r.source.num === 37 && r.source.type === "note").target, "pad:2");
  // a new page (a restart) reads it back; the bridge's name for the port is the same device
  const again = page({}, data);
  again.X._setDevices([{ name: "Minilab3 0", via: "bridge" }], "bridge");
  assert.equal(again.X.personal, true);
  assert.equal(again.X.rowOf({ type: "note", ch: 10, num: 37 }).target, "mirror");
  // export, reset to default, import
  const exported = JSON.parse(again.X.exportJSON());
  assert.equal(exported.version, 2); assert.equal(exported.pages.vj.length, exported.mappings.length);
  again.X.reset();
  assert.equal(again.X.personal, false);
  assert.equal(again.X.rowOf({ type: "note", ch: 10, num: 37 }).target, "pad:2");
  assert.equal(again.X.importJSON(JSON.stringify(exported)), exported.mappings.length);
  assert.equal(again.X.rowOf({ type: "note", ch: 10, num: 37 }).target, "mirror");
  // Remove and Undo put a row back where it was
  const gone = again.X.removeRows(r => r.target === "mirror");
  assert.equal(again.X.rowsOf("mirror").length, 0);
  again.X.putBack(gone);
  assert.equal(again.X.rowsOf("mirror")[0].source.num, 37);
});

test("runtime: a table of the user's own from the first midi.js goes to the first controller of its profile", () => {
  const own = C.profileMapping("minilab3", "vj").map(r => r.source.num === 36 && r.source.type === "note" ? Object.assign({}, r, { target: "mirror", mode: "toggle" }) : r);
  const { X, data } = page({}, { "xeno-midi": JSON.stringify({ profile: "minilab3", mappings: { vj: own } }) });
  assert.equal(X.rowOf({ type: "note", ch: 10, num: 36 }).target, "pad:1");  // no controller yet: the defaults
  X._setDevices([{ name: "Minilab3", via: "Web MIDI" }], "webmidi");
  assert.equal(X.personal, true);
  assert.equal(X.rowOf({ type: "note", ch: 10, num: 36 }).target, "mirror");
  assert.deepEqual(Object.keys(JSON.parse(data["xeno-midi"]).mappings), []);  // taken, not kept twice
  const untouched = page({}, { "xeno-midi": JSON.stringify({ profile: "minilab3", mappings: { vj: C.legacyFactory("minilab3", "vj") } }) });
  untouched.X._setDevices([{ name: "Minilab3", via: "Web MIDI" }], "webmidi");
  assert.equal(untouched.X.personal, false);
  assert.equal(untouched.X.rowOf({ type: "note", ch: 10, num: 36 }).target, "pad:1");  // the new hold pads come in
});
