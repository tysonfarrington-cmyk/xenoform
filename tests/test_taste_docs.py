"""docs/TASTE.md explains every rule of the taste file, in plain words and with its day, and how to add one."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "TASTE.md").read_text(encoding="utf-8")
RULES = json.loads((ROOT / "configs" / "taste.json").read_text(encoding="utf-8"))["rules"]


def test_every_rule_is_explained_with_its_day():
    for r in RULES:
        assert f"`{r['id']}`" in DOC, r["id"]
        _, month, day = r["since"].split("-")
        row = next((line for line in DOC.splitlines() if f"`{r['id']}`" in line), "")
        if row.startswith("|"):  # a table row carries its day
            assert re.search(rf"\b{int(day)} {dict(zip(('10', '11'), ('Oct', 'Nov')))[month]}\b", row), r["id"]


def test_the_doc_says_how_to_add_a_rule_and_what_it_never_does():
    assert "## Adding a rule" in DOC and "configs/taste.json" in DOC and "XENO_TASTE" in DOC
    assert "never" in DOC.lower() and "Breathe stays off by default" in DOC
    for hook in ("guardrails.apply", "morph_pass.pick_stills", "boundary_fx.pick", "beatfx.resolve_dance_preset",
                 "transitions_fx.guard", "dense.recut_from_cache", "[taste]"):
        assert hook in DOC, hook


def test_no_quotes_from_the_sessions():
    low = DOC.lower()
    for phrase in ("pretty terrible", "sparingly and subtly", "handycam", "looks off", "too random", "ruins the consistency",
                   "the more natural stuff", "ugly", "msg "):
        assert phrase not in low, phrase
    assert '"' not in re.sub(r"`[^`]*`", "", DOC), "the doc quotes nobody: its only quotation marks are in code"
