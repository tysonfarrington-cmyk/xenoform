/* Beat-cut windows. Judges and Simple share this. No picture is drawn here. */
(function () {
  function windows(duration, beats, energy) {
    const length = duration || 1;
    const sections = [];
    for (let start = 0; start < length - 0.2; start += 4) {
      sections.push({ start: start, end: Math.min(length, start + 4) });
    }
    if (!sections.length) sections.push({ start: 0, end: length });
    else sections[sections.length - 1].end = length;
    const level = Math.max(0, Math.min(1, Number(energy) || 0));
    const clock = (beats || []).filter((beat) => beat > 0 && beat < length - 0.05);
    const sectionCount = Math.max(1, sections.length);
    if (level <= 0 || !clock.length) {
      return sections.map((section) => [section.start, section.end]);
    }
    const cap = Math.min(Math.max(clock.length, sectionCount), sectionCount * 4, 24);
    let count = sectionCount + Math.round(level * (cap - sectionCount));
    count = Math.max(sectionCount, Math.min(cap, count));
    let picks = [];
    if (count - 1 >= clock.length) picks = clock.slice();
    else {
      for (let index = 1; index < count; index += 1) {
        const slot = Math.min(clock.length - 1, Math.max(0, Math.round((index * clock.length) / count) - 1));
        picks.push(clock[slot]);
      }
      picks = Array.from(new Set(picks)).sort((a, b) => a - b);
    }
    const bounds = [0];
    picks.forEach((beat) => {
      if (beat - bounds[bounds.length - 1] >= 0.18) bounds.push(beat);
    });
    if (length - bounds[bounds.length - 1] < 0.18) bounds[bounds.length - 1] = length;
    else bounds.push(length);
    const rows = [];
    for (let index = 0; index < bounds.length - 1; index += 1) rows.push([bounds[index], bounds[index + 1]]);
    return rows;
  }

  function morphs(rows, energy, drops) {
    const allowed = Math.min(2, Math.round(Math.max(0, Math.min(1, Number(energy) || 0)) * 2));
    if (!allowed || !rows || rows.length < 2) return [];
    const marks = drops && drops.length ? drops : [0.66];
    const ranked = rows
      .map((window, index) => ({ index: index, start: window[0] }))
      .filter((row) => row.index > 0)
      .sort((a, b) => {
        const da = Math.min.apply(null, marks.map((drop) => Math.abs(a.start - drop)));
        const db = Math.min.apply(null, marks.map((drop) => Math.abs(b.start - drop)));
        return da - db;
      });
    return ranked.slice(0, allowed).map((row) => row.index);
  }

  const shots = ["wide", "medium", "close", "reveal"];

  window.XENO_CUT = {
    shots: shots,
    windows: windows,
    morphs: morphs,
    shot: function (index) {
      return shots[index % shots.length];
    },
  };
})();
