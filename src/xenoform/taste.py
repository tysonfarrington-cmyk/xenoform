"""Tys's taste as data: ``configs/taste.json``, the standing rules every Make and every re-cut obeys (docs/TASTE.md,
docs/MUSIC_VIDEO_PLAN.md section 4).

The file is a list of rules; each has an ``id``, a ``kind``, its data and a one-line ``reason`` (and the day it came from,
``since``). Six kinds:

- ``subject``: stills whose noun holds one of ``words`` (as whole words, ``except`` phrases spared) are never picked by
  the app; a still the user pins, types or brings stays theirs;
- ``family``: whole catalogue families (``configs/subjects.json``) never picked, and never grown for a cut;
- ``run``: at most ``max`` stills of a group (``families`` and ``words``) in one cut: the musical run;
- ``look``: a look kept but demoted (``demote``): a ``note`` on a vibe, ``stills`` sent to the back of a vibe's pool, or an
  ``effect`` that steps aside on the shots it reads badly on;
- ``limit``: a cap on a knob or a picker (the Chaos under Breathe, the opener's Intensity, the flash looks before the first
  drop, the slices, the handoff kinds, one effect at a time, no object or vibe twice, clips or objects, one palette);
- ``weight``: the order families are drawn in (natural and iconic first).

``load()`` reads the file, cached on its modification time, so an edit lands at the next Make with no restart. A missing
or broken file means no rules and one warning in the log, never an error: every hook then does exactly what it did before
the taste file (tests/test_taste_absent.py holds the mainline's cut to that). ``XENO_TASTE`` points at another file.

The hooks call the helpers here; what a rule did in a Make is said in ``[taste]`` lines: the guardrail's report for what
it changed in the body (``guard_body``), and the lines a Make or a re-cut gathers while it runs (``collecting``, ``note``)
for what the pick and the pickers did, kept in the record's ``taste`` block and shown on the desk.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

log = logging.getLogger("xenoform")

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "configs" / "taste.json"
ENV = "XENO_TASTE"
KINDS = ("subject", "family", "run", "look", "limit", "weight")
DEMOTES = ("note", "stills", "effect")
EMPTY: dict = {"version": 0, "rules": [], "by_id": {}, "path": ""}

_CACHE: dict[str, tuple[tuple, dict]] = {}
_WARNED: set = set()


# ------------------------------------------------------------------------------------------------ the file


def path() -> Path:
    """The taste file: ``XENO_TASTE`` when set, else ``configs/taste.json``."""
    raw = os.environ.get(ENV, "").strip()
    return Path(raw) if raw else PATH


def _warn_once(key: tuple, message: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    log.warning(message)


def _strings(value) -> list[str]:
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, (list, tuple)) else []


def _clean(raw: Any, where: str) -> dict:
    """The file's valid rules: a rule needs an id, a known kind and a reason; ``off: true`` drops it; an id twice keeps
    its first row. A bad row is left out with a warning, the others hold."""
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise ValueError("no list of rules")
    rules: list[dict] = []
    by_id: dict[str, dict] = {}
    bad: list[str] = []
    for row in raw["rules"]:
        if not isinstance(row, dict):
            bad.append(repr(row)[:40])
            continue
        rid, kind, reason = str(row.get("id") or "").strip(), str(row.get("kind") or "").strip(), str(row.get("reason") or "").strip()
        if not rid or kind not in KINDS or not reason:
            bad.append(rid or repr(row)[:40])
            continue
        if row.get("off") is True or rid in by_id:
            continue
        rule = dict(row)
        for key in ("words", "except", "families", "looks", "skip"):
            if key in rule:
                rule[key] = _strings(rule[key])
        rules.append(rule)
        by_id[rid] = rule
    if bad:
        _warn_once((where, "bad", tuple(bad)), f"taste file {where}: {len(bad)} rule(s) without an id, a known kind or a reason "
                                               f"left out ({', '.join(bad[:5])})")
    banned = []
    for row in raw.get("banned_clips") or [] if isinstance(raw.get("banned_clips"), list) else []:
        if not isinstance(row, dict) or row.get("off") is True:
            continue
        cid, label = str(row.get("id") or "").strip(), str(row.get("label") or "").strip()
        if cid or label:
            banned.append({**row, "id": cid, "label": label})
    return {"version": raw.get("version", 0), "rules": rules, "by_id": by_id, "path": where, "banned_clips": banned}


def load() -> dict:
    """The taste file's rules (``{"version", "rules", "by_id", "path"}``), read again only when the file changes. A
    missing or broken file is ``EMPTY`` (no rules) with one warning in the log."""
    p = path()
    try:
        st = p.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        _warn_once((str(p), "missing"), f"taste file {p} not found: no taste rules")
        return EMPTY
    hit = _CACHE.get(str(p))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        data = _clean(json.loads(p.read_text(encoding="utf-8")), str(p))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        _warn_once((str(p), "broken", stamp), f"taste file {p} unreadable ({exc}): no taste rules")
        data = EMPTY
    _CACHE[str(p)] = (stamp, data)
    return data


def rules(kind: str | None = None) -> list[dict]:
    """Every rule, or every rule of one ``kind``, in file order."""
    got = load()["rules"]
    return [r for r in got if r.get("kind") == kind] if kind else list(got)


def rule(rid: str) -> dict | None:
    """One rule by its id, or None when the file has no such rule (or no file)."""
    return load()["by_id"].get(str(rid))


def active() -> bool:
    """True when the taste file has a rule."""
    return bool(load()["rules"])


def _limit(rid: str) -> dict | None:
    r = rule(rid)
    return r if r and r.get("kind") == "limit" else None


# ------------------------------------------------------------------------------------------------ the lines


_LINES: contextvars.ContextVar[list | None] = contextvars.ContextVar("xenoform_taste_lines", default=None)


@contextmanager
def collecting():
    """Gather the ``[taste]`` lines the hooks note while a Make or a re-cut runs (``note``); yields the list."""
    got: list[dict] = []
    token = _LINES.set(got)
    try:
        yield got
    finally:
        _LINES.reset(token)


def current() -> list[dict] | None:
    """The lines the running Make has gathered so far (None outside one)."""
    return _LINES.get()


def say(rid: str | list[str], text: str) -> str:
    """A ``[taste]`` line: the sentence, then the rule (or rules) it speaks for in brackets."""
    ids = [rid] if isinstance(rid, str) else list(rid)
    return f"[taste] {text} ({', '.join(ids)})"


def note(rid: str | list[str], text: str) -> None:
    """One ``[taste]`` line for the running Make (nothing when none is collecting, as for a preview). ``rid`` is the rule,
    or the rules, the line speaks for."""
    got = _LINES.get()
    if got is None:
        return
    ids = [str(rid)] if isinstance(rid, str) else [str(r) for r in rid]
    line = say(ids, text)
    for x in got:
        if x["line"] == line:
            return
    got.append({"ids": ids, "line": line})


def lines(got: list[dict] | None) -> list[str]:
    return [x["line"] for x in got or []]


def fired(got: list[dict] | None) -> list[str]:
    """The ids of the rules the lines speak for, in the order they first fired."""
    return list(dict.fromkeys(i for x in got or [] for i in x["ids"]))


def record(got: list[dict] | None) -> dict:
    """The record's ``taste`` block: which file, the rules that fired and their lines."""
    return {"file": load().get("path") or str(path()), "rules": len(rules()), "fired": fired(got), "lines": lines(got)}


def layered(layers: Iterable[tuple[str, Iterable[str]]]) -> dict:
    """A Stems Make's ``taste`` block (``stems_mode.run``): every layer is a cut of its own that the hooks act in, so each
    layer's ``[taste]`` lines come up named by its stem ("[taste] drums layer: ..."), the rules they speak for kept."""
    got: list[dict] = []
    for stem, said in layers:
        for line in said or []:
            text = str(line)
            if not text.startswith("[taste] "):
                continue
            body = text[len("[taste] "):]
            ids: list[str] = []
            if body.endswith(")") and " (" in body:
                body, tail = body[:body.rindex(" (")], body[body.rindex(" (") + 2:-1]
                ids = [i.strip() for i in tail.split(",") if i.strip()]
            got.append({"ids": ids, "line": say(ids, f"{stem} layer: {body}") if ids else f"[taste] {stem} layer: {body}"})
    return record(got)


# ------------------------------------------------------------------------------------------------ nouns


def words_of(text: Any) -> str:
    """A noun or a phrase as plain words: lowercase letters and digits, one space between (``t-rex skull`` is
    ``t rex skull``), so a rule's words match whole words only (``cup`` never matches ``cupola``)."""
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _has(phrase: str, text: str) -> bool:
    p = words_of(phrase)
    return bool(p) and f" {p} " in f" {text} "


def _family(noun: str) -> str:
    try:
        from xenoform import stills

        return stills.family_of(noun)
    except Exception:
        return ""


_JOINS = re.compile(r"\s(?:with|holding|of|on|in|under|from|made|full|into|topped|carved|crowned|perched|curled|mid)\s")


def head_of(text: str) -> str:
    """The head of a described noun, as plain words: what it is before what it has (``dragon skull with curling horns``
    is a ``dragon skull``), the way ``stills.noun_keys`` reads one."""
    return _JOINS.split(" " + words_of(text) + " ", maxsplit=1)[0].strip()


def _matches(r: dict, text: str) -> bool:
    """A rule's words in ``text`` (plain words), none of its ``except`` phrases there. A rule with ``head: true`` reads
    only the noun's head and wants a word at its end: ``ram golden horn`` is a horn, ``horned demon skull`` and ``dragon
    skull with curling horns`` are skulls."""
    if r.get("head"):
        head = head_of(text)
        hit = any(f" {head}".endswith(f" {words_of(w)}") for w in r.get("words") or [] if words_of(w))
    else:
        hit = any(_has(w, text) for w in r.get("words") or [])
    return hit and not any(_has(x, text) for x in r.get("except") or [])


def ban_for(noun: Any, family: str | None = None) -> dict | None:
    """The rule that keeps ``noun`` out of the app's picks (a ``subject`` whose words it holds, a ``family`` it belongs to),
    or None. ``family`` is the catalogue family when the caller has it."""
    text = words_of(noun)
    if not text:
        return None
    for r in rules("subject"):
        if _matches(r, text):
            return r
    fams = rules("family")
    if fams:
        fam = family if family is not None else _family(str(noun))
        for r in fams:
            if fam and fam in (r.get("families") or []):
                return r
    return None


def noun_ok(noun: Any, family: str | None = None) -> bool:
    """False for a noun the taste file keeps out of the picks and the grows."""
    return ban_for(noun, family) is None


def run_for(noun: Any, family: str | None = None) -> dict | None:
    """The ``run`` rule whose group ``noun`` belongs to (its family or its words), or None."""
    runs = rules("run")
    if not runs:
        return None
    text = words_of(noun)
    fam = family if family is not None else _family(str(noun))
    for r in runs:
        if (fam and fam in (r.get("families") or [])) or _matches(r, text):
            return r
    return None


def _row_noun(row: dict) -> str:
    return str((row or {}).get("noun") or "")


def _row_family(row: dict) -> str:
    fam = (row or {}).get("family")
    return str(fam) if fam is not None else _family(_row_noun(row))


# ------------------------------------------------------------------------------------------------ the family weight


def _weight_rule() -> dict | None:
    got = rules("weight")
    return got[0] if got else None


def weight(family: Any) -> float:
    """The family's weight in the taste file (``natural-first``): above 1 drawn earlier, under 1 later; 1.0 with no file."""
    r = _weight_rule()
    if not r:
        return 1.0
    try:
        return float((r.get("weights") or {}).get(str(family or ""), r.get("default", 1.0)))
    except (TypeError, ValueError):
        return 1.0


def first_at() -> float | None:
    r = _weight_rule()
    try:
        return float(r.get("first_at", 1.5)) if r else None
    except (TypeError, ValueError):
        return 1.5


def tier(family: Any) -> int:
    """0 for a family drawn first (its weight at ``first_at`` or more), 1 for the rest; 0 for every family with no file,
    so a sort on it keeps the order it had."""
    top = first_at()
    if top is None:
        return 0
    return 0 if weight(family) >= top else 1


def by_weight(rows: list[dict]) -> list[dict]:
    """``rows`` with the heavier families first, stable within a weight (the order the caller gave stays inside each)."""
    if not _weight_rule():
        return rows
    return sorted(rows, key=lambda r: -weight(_row_family(r)))


def realm_weight(rows: list[dict]) -> float:
    """A realm's weight for the cut: the mean of its rows' family weights."""
    if not rows:
        return 0.0
    return sum(weight(_row_family(r)) for r in rows) / len(rows)


def first_realms(names: Iterable[str], by_realm: dict[str, list[dict]]) -> list[str]:
    """The realms of ``names`` whose families weigh at least ``first_at`` on average (creatures, garden, cosmos, dark
    fantasy before machines and the home): the ones a cut with no line draws on first. [] with no weight rule, or when no
    realm reaches it (then every realm takes its turn, as before)."""
    top = first_at()
    if top is None:
        return []
    return [n for n in names if realm_weight(by_realm.get(n) or []) >= top]


def family_weights(weights: dict[str, float]) -> dict[str, float]:
    """A vibe's family weights (``configs/subjects.json``) times the taste file's, banned families out: what the cut's
    family and a grow draw on. Unchanged with no file."""
    if not active():
        return weights
    out = {}
    for fam, w in weights.items():
        if any(fam in (r.get("families") or []) for r in rules("family")):
            continue
        out[fam] = float(w) * weight(fam)
    return out


# ------------------------------------------------------------------------------------------------ the pick


def screen(rows: list[dict], exempt: Callable[[dict], bool] | None = None) -> tuple[list[dict], list[tuple[dict, dict]]]:
    """``rows`` without the stills the taste file bans (``ban_for``), the order kept; ``exempt`` spares a row (a shape the
    user typed or asked for). Returns the rows kept and the ``(row, rule)`` pairs left out."""
    if not active():
        return rows, []
    kept, dropped = [], []
    for r in rows:
        hit = None if (exempt and exempt(r)) else ban_for(_row_noun(r), _row_family(r))
        if hit:
            dropped.append((r, hit))
        else:
            kept.append(r)
    return kept, dropped


def note_dropped(dropped: list[tuple[dict, dict]], vibe: str) -> None:
    """One line for the stills a pick left out, the objects by name under the rule that kept each out."""
    if not dropped:
        return
    by: dict[str, list[str]] = {}
    for row, r in dropped:
        by.setdefault(r["id"], []).append(_row_noun(row))
    parts = []
    for rid, nouns in by.items():  # each rule with the objects it kept out, so the line says which did what
        names = list(dict.fromkeys(nouns))
        parts.append(f"{rid}: {', '.join(names[:6])}{', ...' if len(names) > 6 else ''}")
    n = len(dropped)
    note(list(by), f"{n} {vibe} still{'s' if n != 1 else ''} left out of the pick; " + "; ".join(parts))


def _palette_rule() -> dict | None:
    return _limit("one-palette")


def _demoted_rows_rule(vibe: str) -> list[dict]:
    return [r for r in rules("look") if r.get("demote") == "stills" and str(r.get("vibe") or "") == str(vibe or "")]


def settle(pool: list[dict], *, vibe: str, taken: Iterable[str] = ()) -> list[dict]:
    """The pool in the order a cut takes it, with what the taste file says goes last moved to the back (the order kept
    otherwise, so the first ``count`` rows are the chain): a second still of an object the cut already has (``taken``:
    the pinned stills, your images and shapes; ``no-object-twice``), a run's stills past its ``max`` (``run``), a vibe's
    demoted stills (``look`` with ``demote: stills``) and stills off the vibe's palette (``one-palette``). Nothing is
    dropped: a pool too small for the cut walks into the back rows rather than repeat."""
    if not active() or not pool:
        return pool
    front, back = [], []
    seen = {words_of(n) for n in taken if words_of(n)}
    runs: dict[str, int] = {}
    once = _limit("no-object-twice") is not None
    demote = _demoted_rows_rule(vibe)
    fits = palette_check(vibe, pool)
    counts = {"repeats": 0, "runs": 0, "demoted": 0, "palette": 0}
    first_of: dict[str, str] = {}
    for r in pool:
        noun = words_of(_row_noun(r))
        why = ""
        run = None
        if once and noun and noun in seen:
            why = "repeats"
        else:
            run = run_for(_row_noun(r), _row_family(r))
            if run is not None:
                try:
                    cap = int(run.get("max", 1))
                except (TypeError, ValueError):
                    cap = 1
                if runs.get(run["id"], 0) >= cap:
                    why = "runs"
                    first_of.setdefault("runs", run["id"])
            if not why and any(_matches(d, noun) for d in demote):
                why = "demoted"
                first_of.setdefault("demoted", demote[0]["id"])
            if not why and fits is not None and not fits(r):
                why = "palette"
        if why:
            counts[why] += 1
            back.append(r)
        else:
            front.append(r)
            if noun:
                seen.add(noun)
            if run is not None:  # a run's place is taken only by a still that stays in front
                runs[run["id"]] = runs.get(run["id"], 0) + 1
    if counts["repeats"]:
        note("no-object-twice", f"{counts['repeats']} still{'s' if counts['repeats'] != 1 else ''} of an object already in the cut "
                                f"moved to the back of the {vibe} pool: no object twice")
    if counts["runs"]:
        note(first_of["runs"], f"{counts['runs']} more instrument{'s' if counts['runs'] != 1 else ''} moved to the back: one "
                               f"a cut, no musical run")
    if counts["demoted"]:
        note(first_of["demoted"], f"{counts['demoted']} demoted {vibe} still{'s' if counts['demoted'] != 1 else ''} moved to the back "
                                  f"of the pool")
    if counts["palette"]:
        note("one-palette", f"{counts['palette']} still{'s' if counts['palette'] != 1 else ''} off the {vibe} palette moved to the "
                            f"back: one palette a cut")
    return front + back


def usable(rows: list[dict]) -> list[dict]:
    """The rows a cut may draw on without breaking a rule: no banned still, one still an object, a run's stills up to its
    ``max``. What the chain's morph count is planned on (``dense.long_song_chain``, the desk's estimate), so a pool the
    bans shrink plans fewer morphs instead of repeating a still. ``rows`` as they are with no file."""
    if not active():
        return rows
    kept, _ = screen(rows)
    out, seen, runs = [], set(), {}
    once = _limit("no-object-twice") is not None
    for r in kept:
        noun = words_of(_row_noun(r))
        if once and noun and noun in seen:
            continue
        run = run_for(_row_noun(r), _row_family(r))
        if run is not None:
            try:
                cap = int(run.get("max", 1))
            except (TypeError, ValueError):
                cap = 1
            if runs.get(run["id"], 0) >= cap:
                continue
            runs[run["id"]] = runs.get(run["id"], 0) + 1
        seen.add(noun)
        out.append(r)
    return out


def distinct(stills: list[dict]) -> int:
    """How many different stills a chain holds: by file as ever, and by object when the taste file says no object twice."""
    by_path = len({str(s.get("path")) for s in stills})
    if _limit("no-object-twice") is None:
        return by_path
    nouns = {words_of(_row_noun(s)) or str(s.get("path")) for s in stills}
    return min(by_path, len(nouns))


# ------------------------------------------------------------------------------------------------ the palette


_PALETTES: dict[tuple, tuple[float, list[float]] | None] = {}
NEUTRAL_SHARE = 0.04   # under this share of colourful pixels a still is neutral (black glass, chrome, ivory): it fits any palette
COLOURFUL_SHARE = 0.12  # a neutral vibe's still with this much colour is off its palette (the pink rose among black glass)
NEUTRAL_VIBE = 0.6     # a vibe whose own stills are this neutral has a neutral palette


def palette_of(file: Any) -> tuple[float, list[float]] | None:
    """A still's colour: the share of its pixels that carry colour (saturation over a quarter, not dark) and their hue
    histogram in 12 bins of 30 degrees, read from a 64x36 copy; cached on the file's size and time. None when unreadable."""
    try:
        st = os.stat(str(file))
    except OSError:
        return None
    key = (str(file), st.st_mtime_ns, st.st_size)
    if key in _PALETTES:
        return _PALETTES[key]
    try:
        import numpy as np
        from PIL import Image

        with Image.open(str(file)) as im:
            im.draft("RGB", (128, 72))
            a = np.asarray(im.convert("RGB").resize((64, 36)), dtype=np.float32) / 255.0
        mx, mn = a.max(axis=2), a.min(axis=2)
        delta = mx - mn
        sat = np.where(mx > 1e-6, delta / np.maximum(mx, 1e-6), 0.0)
        mask = (sat > 0.25) & (mx > 0.2)
        share = float(mask.mean())
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        d = np.maximum(delta, 1e-6)
        hue = np.where(mx == r, ((g - b) / d) % 6.0, np.where(mx == g, (b - r) / d + 2.0, (r - g) / d + 4.0)) * 60.0
        hist, _ = np.histogram(hue[mask], bins=12, range=(0.0, 360.0), weights=(sat * mx)[mask])
        total = float(hist.sum())
        out = (round(share, 4), [round(float(x) / total, 4) for x in hist] if total > 0 else [0.0] * 12)
    except Exception:
        out = None
    _PALETTES[key] = out
    return out


def _registry_palette(vibe: str) -> str:
    try:
        from xenoform import vibes as _v

        return str((_v.get(vibe) or {}).get("palette") or "")
    except Exception:
        return ""


def palette_check(vibe: str, pool: list[dict]) -> Callable[[dict], bool] | None:
    """For the ``one-palette`` rule, a test a still passes when it sits on the vibe's palette, measured from the vibe's
    shipped stills (else its pool): a neutral still always fits; on a neutral vibe a colourful still does not; else its
    hues must overlap the vibe's by ``min_overlap``. None when the rule is off, the vibe's registry palette is one of its
    ``skip`` (None's natural colours, a rainbow), or the vibe has too few readable stills to say."""
    r = _palette_rule()
    if not r or _registry_palette(vibe) in (r.get("skip") or []):
        return None
    anchor = [x for x in pool if x.get("shipped")] or list(pool)
    measured = [m for m in (palette_of(x.get("path") or "") for x in anchor[:48]) if m is not None]
    if len(measured) < 4:
        return None
    neutral = sum(1 for share, _ in measured if share < NEUTRAL_SHARE) / len(measured)
    hist = [0.0] * 12
    colourful = [h for share, h in measured if share >= NEUTRAL_SHARE]
    for h in colourful:
        for k in range(12):
            hist[k] += h[k] / len(colourful)
    try:
        need = float(r.get("min_overlap", 0.3))
    except (TypeError, ValueError):
        need = 0.3

    def fits(row: dict) -> bool:
        if row.get("pinned") or row.get("user") or row.get("own"):
            return True
        got = palette_of(row.get("path") or "")
        if got is None:
            return True
        share, h = got
        if share < NEUTRAL_SHARE:
            return True
        if neutral >= NEUTRAL_VIBE:
            return share < COLOURFUL_SHARE
        if not colourful:
            return True
        return sum(min(a, b) for a, b in zip(h, hist)) >= need

    return fits


# ------------------------------------------------------------------------------------------------ the looks


def demoted_vibe(vibe: Any) -> dict | None:
    """The ``look`` rule that demotes a whole vibe (a note: it stays, chosen by name), or None."""
    v = str(vibe or "")
    return next((r for r in rules("look") if r.get("demote") == "note" and str(r.get("vibe") or "") == v and v), None)


def living(noun: Any, family: str | None = None) -> bool:
    """True for a living thing as the kaleido rule reads one (its families, or a word of it)."""
    r = rule("no-kaleido-on-living")
    if not r:
        return False
    fam = family if family is not None else _family(str(noun))
    if fam and fam in (r.get("families") or []):
        return True
    return _matches(r, words_of(noun))


def flash_looks() -> tuple[tuple[str, ...], str] | None:
    """The flash looks no shot before the first drop plays, and the look they stand down to; None when the rule is off."""
    r = _limit("no-flash-before-drop")
    if not r:
        return None
    return tuple(r.get("looks") or ()), str(r.get("calm") or "cool-echo")


def calm_look(preset: str, index: int, house: dict | None) -> str:
    """The look a shot before the first drop plays instead of ``preset`` (the cut's resolved look), or "" to keep it: a
    flash look stands down to the rule's calm look, and the house look's opening role (its flash on a cut's first shot)
    to the house's VJ preset."""
    got = flash_looks()
    if not got:
        return ""
    looks, calm = got
    preset = str(preset or "")
    if preset in looks:
        return calm
    if preset == "house" and index == 0:
        intro = str((((house or {}).get("dance_fx") or {}).get("intro") or {}).get("preset") or "")
        if intro in looks:
            vj = str((((house or {}).get("dance_fx") or {}).get("vj") or {}).get("preset") or calm)
            return vj if vj not in looks else calm
    return ""


def slices_instead() -> str:
    """What the sliced foreshadow becomes (``no-slices``), or "" when the rule is off."""
    r = _limit("no-slices")
    return str(r.get("instead") or "trace") if r else ""


def kind_limits() -> dict:
    """The handoff kinds' limits for ``boundary_fx.pick``: ``wipe_share`` (at most this share of the handoffs are wipes),
    ``strobe_heat`` (a strobe only on a boundary this hot) and ``no_repeat`` (never the kind just used). None or False
    where the taste file says nothing."""
    out: dict = {"wipe_share": None, "strobe_heat": None, "no_repeat": False}
    r = _limit("wipes-a-quarter")
    if r:
        try:
            out["wipe_share"] = max(0.0, min(1.0, float(r.get("share", 0.25))))
        except (TypeError, ValueError):
            out["wipe_share"] = 0.25
    r = _limit("strobe-at-full-heat")
    if r:
        try:
            out["strobe_heat"] = float(r.get("heat", 1.0))
        except (TypeError, ValueError):
            out["strobe_heat"] = 1.0
    out["no_repeat"] = _limit("no-kind-twice") is not None
    return out


def opener() -> tuple[float, float] | None:
    """(the opener's Intensity cap, the most seconds an opener lasts), or None when the rule is off."""
    r = _limit("quiet-opener")
    if not r:
        return None
    try:
        return float(r.get("max", 0.6)), float(r.get("seconds", 20.0))
    except (TypeError, ValueError):
        return 0.6, 20.0


def breathe_chaos() -> float | None:
    """The Chaos cap under Breathe, or None."""
    r = _limit("breathe-chaos-cap")
    if not r:
        return None
    try:
        return float(r.get("max", 0.5))
    except (TypeError, ValueError):
        return 0.5


def one_effect() -> int | None:
    """How many effects a shot plays at once (``one-effect``), or None."""
    r = _limit("one-effect")
    if not r:
        return None
    try:
        return max(1, int(r.get("effects", 1)))
    except (TypeError, ValueError):
        return 1


def no_mix() -> bool:
    return _limit("clips-or-objects") is not None


def clips_once() -> bool:
    """True when no clip shows twice in a clips cut (``no-clip-twice``): ``clip_cut.fit`` plans fewer, longer shots."""
    return _limit("no-clip-twice") is not None


def banned_clips() -> list[dict]:
    """The taste file's ``banned_clips``: the clips no cut shows, each by its film pack id and its label (1 Nov: the
    Keaton bridge, the Keaton cannon and the Potemkin steps); [] with no file."""
    return list(load().get("banned_clips") or [])


def clip_banned(clip: Any) -> dict | None:
    """The ``banned_clips`` entry a clip matches, or None: by its pack id (a file named ``NN_<id>.mp4``, as the film pack
    names it, or ``<id>.mp4``) or by its label (its words, as the chain reads them), so a folder that still holds the
    old file, renamed or not, never plays it."""
    rows = banned_clips()
    if not rows:
        return None
    if isinstance(clip, dict):
        path, label = str(clip.get("path") or ""), str(clip.get("label") or "")
    else:
        path, label = str(clip or ""), ""
    stem = Path(path).stem.lower()
    bare = stem.split("_", 1)[1] if re.match(r"^\d+_", stem) else stem
    said = words_of(label)
    for r in rows:
        cid = str(r.get("id") or "").lower()
        if cid and cid in (stem, bare):
            return r
        if said and words_of(r.get("label")) == said:
            return r
    return None


def vibes_once() -> bool:
    return _limit("no-vibe-twice") is not None


# ------------------------------------------------------------------------------------------------ the knobs


def cap_macros(m: dict, state: dict | None) -> dict:
    """The knobs a Make and a re-cut run on, with the taste file's caps: Chaos at most ``breathe-chaos-cap`` under Breathe
    (the orbit swing and the kick wobble read the cut's Chaos). A new dict; ``m`` as it was with no file or no Breathe."""
    cap = breathe_chaos()
    if cap is None:
        return m
    from xenoform import pacing as _pc

    if not _pc.breathe_of(state or {}):
        return m
    try:
        chaos = float((m or {}).get("chaos", 0.3))
    except (TypeError, ValueError):
        return m
    if chaos <= cap + 1e-9:
        return m
    note("breathe-chaos-cap", f"Chaos {chaos:.2f} capped at {cap:.2f} under Breathe: past it the picture shakes")
    return {**m, "chaos": cap}


def opener_shots(shots: list[dict], drop: float | None = None) -> list[int]:
    """The shots of the cut's opener: its first passage (``pacing.passage_of``), cut at the first drop and at the rule's
    seconds; none when the cut opens on a drop."""
    got = opener()
    if not got or not shots:
        return []
    from xenoform import pacing as _pc

    _, most = got
    passages = _pc.passage_of(shots)
    if str(shots[0].get("section") or "") in ("drop", "drop_late") or str(shots[0].get("boundary") or "") == "drop":
        return []
    first = first_drop(shots, drop)
    end = min(most, first if first is not None else float("inf"))
    return [i for i, (s, p) in enumerate(zip(shots, passages)) if p == passages[0] and float(s.get("start") or 0.0) < end - 1e-6]


def first_drop(shots: list[dict], drop: float | None = None) -> float | None:
    """When the cut's first drop starts: its first shot of a drop role, a drop boundary or a drop run, else the plan's drop
    time (a plan with no roles), else None."""
    for s in shots:
        if str(s.get("section") or "") in ("drop", "drop_late") or str(s.get("boundary") or "") == "drop" \
                or s.get("drop_run") is not None:
            return float(s.get("start") or 0.0)
    return float(drop) if drop is not None else None


def before_drop(shots: list[dict], drop: float | None = None) -> list[int]:
    """The shots no flash look plays on: every shot before the first drop, or with no drop in the cut its opener."""
    first = first_drop(shots, drop)
    if first is None:
        got = opener()
        if not got:
            return [0] if shots else []
        return [i for i, s in enumerate(shots) if float(s.get("start") or 0.0) < got[1] - 1e-6] or [0]
    return [i for i, s in enumerate(shots) if float(s.get("start") or 0.0) < first - 1e-6]


def shot_nouns(shots: list[dict], stills: list) -> list[tuple[str, str]]:
    """The two objects each shot morphs between (its ``morph`` lands on the next still), as nouns; ``stills`` rows with a
    noun or files (``cosmic/042_wolf_skull.jpg``, read as ``wolf skull``). ("", "") where the shot plays no morph of the
    chain."""
    names = []
    for s in stills or []:
        if isinstance(s, dict):
            names.append(_row_noun(s) or Path(str(s.get("file") or s.get("path") or "")).stem)
        else:
            names.append(re.sub(r"^\d+_", "", Path(str(s)).stem).replace("_", " "))
    out = []
    for i, s in enumerate(shots):
        m = s.get("morph", s.get("clip", i))
        try:
            m = int(m)
        except (TypeError, ValueError):
            out.append(("", ""))
            continue
        out.append((names[m], names[m + 1]) if 0 <= m < len(names) - 1 else ("", ""))
    return out


def effects_by_shot(shots: list[dict], names: list[str], stills: list | None = None, turn: int | None = None) -> dict:
    """The cut's effects a shot at a time, in place (``fx_names``, the field the compositor and the timeline read): with
    ``one-effect`` and more than one effect chosen, each passage plays one in turn (a cut with no passages takes them in
    even runs; a whole song's window, one passage, takes its passage's ``turn`` in the song); with
    ``no-kaleido-on-living`` a shot that morphs a living thing plays another of the chosen effects instead of the kaleido,
    or none. A shot that already says its own (Breathe's profile, the timeline) keeps it, the kaleido still stepping
    aside. Returns what it did."""
    names = [n for n in names if n != "smear"]
    did = {"turns": 0, "kaleido": 0}
    if not names:
        return did
    from xenoform import pacing as _pc

    each = one_effect()
    passages = _pc.passage_of(shots)
    order = {p: k + int(turn or 0) for k, p in enumerate(sorted(set(passages)))}
    single = len(order) == 1 and turn is None
    if each is not None and len(names) > each:
        for i, (s, p) in enumerate(zip(shots, passages)):
            if "fx_names" in s:
                continue
            k = (i * len(names)) // max(1, len(shots)) if single else order[p]
            s["fx_names"] = [names[k % len(names)]]
            did["turns"] += 1
        if did["turns"]:
            note("one-effect", f"{len(names)} effects take turns, one a {'stretch' if single else 'passage'} "
                               f"({', '.join(names)}): never two on one look")
    if "kaleido" in names and rule("no-kaleido-on-living"):
        pairs = shot_nouns(shots, stills or [])
        others = [n for n in names if n != "kaleido"]
        for s, (a, b) in zip(shots, pairs):
            mine = list(s["fx_names"]) if "fx_names" in s else list(names)
            if "kaleido" not in mine or not (living(a) or living(b)):
                continue
            rest = [n for n in mine if n != "kaleido"]
            if not rest and others and each is not None:
                rest = [others[0]]
            s["fx_names"] = rest
            did["kaleido"] += 1
        if did["kaleido"]:
            n = did["kaleido"]
            note("no-kaleido-on-living", f"the kaleido steps aside on {n} shot{'s' if n != 1 else ''} that "
                                         f"morph{'' if n != 1 else 's'} a living thing")
    return did


# ------------------------------------------------------------------------------------------------ the batch and the song plan


def fresh_vibes(order: list[str], keep: int = 1) -> list[str]:
    """Vibes for several Makes of one idea (a batch of variations, a song plan): each once (``no-vibe-twice``), the
    demoted ones (``look`` notes on a vibe) out after the first ``keep`` (the vibe the user chose stays). ``order`` as it
    was with no file."""
    if not active():
        return order
    out: list[str] = []
    for k, v in enumerate(order):
        if vibes_once() and v in out:
            continue
        if k >= keep and demoted_vibe(v):
            continue
        out.append(v)
    return out


# ------------------------------------------------------------------------------------------------ the Make body


def _film_pack_dirs() -> list[Path]:
    dirs = [ROOT / "work" / "ui" / "film_pack"]
    try:
        cfg = json.loads((ROOT / "configs" / "film_pack.json").read_text(encoding="utf-8"))
        folder = str(cfg.get("folder") or "")
        if folder:
            p = Path(folder)
            dirs.append(p if p.is_absolute() else ROOT / p)
    except (OSError, ValueError, AttributeError):
        pass
    return dirs


def film_clip(path: Any) -> bool:
    """True for a clip of the free film pack (black-and-white public-domain films)."""
    try:
        p = Path(str(path)).resolve()
    except (OSError, ValueError):
        return False
    for d in _film_pack_dirs():
        try:
            if p.is_relative_to(d.resolve()):
                return True
        except (OSError, ValueError):
            continue
    return "film_pack" in {part.lower() for part in p.parts}


def guard_body(body: dict, rep, *, expert: bool = False) -> None:
    """The taste file's rules on a Make body, in place, through the guardrail's report (``guardrails.apply``): a clamp is a
    ``[taste]`` line in what it applied (a warning instead under Expert, the value kept), a note is a ``[taste]`` warning.
    What the pick and the pickers do during the Make is said by the Make itself."""
    if not active():
        return
    from xenoform import pacing as _pc

    rid = "taste"

    def text(rule_id: str | list[str], sentence: str) -> str:  # the guardrail prints "[taste] " before it
        return say(rule_id, sentence)[len("[taste] "):]

    clips = str(body.get("morph_source") or "").strip().lower() == "clips"
    # clips or objects: a clips cut takes only clips, an object cut only objects (hard: the two never share a cut). In
    # Stems mode the rule holds within a layer and an objects layer may overlap a clips layer (decision 10 of the plan,
    # 31 Oct): the layers are their own Makes, so the body as a whole is not clamped
    stems_mode = str(body.get("mode") or "").strip().lower() == "stems"
    if no_mix() and not stems_mode:
        if clips and (body.get("morph_targets") or body.get("chain_pins")):
            rep.clamp(rid, text("clips-or-objects", "a clips cut takes only your clips: its images and pinned stills were left out"),
                      hard=True)
            body["morph_targets"] = []
            body["chain_pins"] = {}
        if not clips and [c for c in body.get("own_clips") or [] if c]:
            rep.clamp(rid, text("clips-or-objects", f"an object cut takes no clips: {len(body['own_clips'])} clip(s) left out"),
                      hard=True)
            body["own_clips"] = []
    # Chaos under Breathe
    cap = breathe_chaos()
    m = body.get("macros") if isinstance(body.get("macros"), dict) else None
    if cap is not None and m is not None and _pc.breathe_of(body):
        try:
            chaos = float(m.get("chaos", 0.3))
        except (TypeError, ValueError):
            chaos = 0.3
        if chaos > cap + 1e-9 and rep.clamp(rid, text("breathe-chaos-cap", f"Chaos {chaos:.2f} under Breathe is capped at "
                                                                         f"{cap:.2f}: past it the picture shakes")):
            body["macros"] = {**m, "chaos": cap}
    # the sliced foreshadow
    instead = slices_instead()
    if instead and str(body.get("foreshadow") or "").strip().lower() == "slices":
        if rep.clamp(rid, text("no-slices", f"the sliced foreshadow draws bars: {instead} instead")):
            body["foreshadow"] = instead
    if clips:
        own = [c for c in body.get("own_clips") or [] if c]
        gone = [c for c in own if clip_banned(c)]
        if gone:  # a clip the taste file bans never plays, under Expert too: Tys took it out of the pack (1 Nov)
            names = ", ".join(str((c.get("label") if isinstance(c, dict) else "") or Path(str((c or {}).get("path") if isinstance(c, dict) else c)).stem)
                              for c in gone)
            rep.clamp(rid, text("banned_clips", f"{len(gone)} clip{'s' if len(gone) != 1 else ''} the taste file bans left out: {names}"),
                      hard=True)
            body["own_clips"] = own = [c for c in own if not clip_banned(c)]
        films = [c for c in own if film_clip((c or {}).get("path") if isinstance(c, dict) else c)]
        if films and rule("no-film-clips"):
            rep.warn(rid, text("no-film-clips", f"{len(films)} of your clips come from the free film pack: black-and-white film "
                                                f"reads flat in a music video"))
        return
    # notes: what the Make will do with the body as it is
    r = demoted_vibe(body.get("vibe"))
    if r:
        rep.warn(rid, text(r["id"], f"{body.get('vibe')} is a demoted vibe: it works when chosen, but it is off the featured cards"))
    got = opener()
    if got and m is not None:
        try:
            inten = float(m.get("intensity", 0.5))
        except (TypeError, ValueError):
            inten = 0.5
        if inten > got[0] + 1e-9:
            rep.warn(rid, text("quiet-opener", f"Intensity {inten:.2f}: the opening passage plays at {got[0]:.2f}, a quiet hook"))
    looks = flash_looks()
    look = str(body.get("dance_fx") or "").strip().lower()
    if looks and look in looks[0]:
        rep.warn(rid, text("no-flash-before-drop", f"the {look} look stands down to {looks[1]} before the first drop"))
    names = [n for n in (body.get("effects") or []) if isinstance(n, str) and n != "smear"] if isinstance(body.get("effects"), list) else []
    each = one_effect()
    if each is not None and len(names) > each:
        rep.warn(rid, text("one-effect", f"{len(names)} effects chosen: they take turns, one a passage, never two on one look"))
    if "kaleido" in names and rule("no-kaleido-on-living"):
        rep.warn(rid, text("no-kaleido-on-living", "the kaleido steps aside on shots that morph a living thing"))
    typed = words_of(" ".join(str(body.get(k) or "") for k in ("idea", "own_shapes")))
    named = sorted({r2["id"] for r2 in rules("subject") if _matches(r2, typed)})
    if named:
        rep.warn(rid, text(named, "your line names what the taste file bans: what you type still leads, the app's own picks "
                                  "leave it out"))
