"""A loved chain is pins (configs/chain_presets.json): under the taste file its stills hold their slots, none of them is
a banned subject, and the slots it leaves open are picked by the taste file's rules."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from xenoform import morph_pass as mp
from xenoform import presets, taste

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def shipped(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(ROOT / "configs" / "taste.json"))


def _noun(file: str) -> str:
    return re.sub(r"^\d+_", "", Path(file).stem).replace("_", " ")


def test_no_loved_chain_pins_a_banned_subject(shipped):
    for p in presets.load():
        for slot, file in p["pins"].items():
            assert taste.ban_for(_noun(file)) is None, (p["id"], slot, file)


def test_a_loved_chain_holds_its_pins_and_the_rest_obey_the_taste_file(shipped):
    rose = presets.get("black-rose")
    assert rose and rose["pins"], "the black glass rose ships its pins (the shipped black pool)"
    with taste.collecting():
        _, picked = mp.pick_stills(presets.body(rose), 10, record=False)
    for slot, file in rose["pins"].items():
        assert picked[int(slot)]["file"] == file and picked[int(slot)]["pinned"]
    free = [r for k, r in enumerate(picked) if str(k) not in rose["pins"]]
    assert all(taste.ban_for(r["noun"]) is None for r in free)
    assert "dna helix" not in [r["noun"] for r in free]  # the black pool's helix stays out of the open slots
