"""One desk, the server halves (docs/WORKFLOW_AUDIT.md, fixes C2 and F2): the transition guard reports one line a kind
instead of one a boundary, the 9:16 default resolves to native without a guardrail line, and a director animatic with a
vibe cuts the vibe's stills instead of painting blocks."""

from pathlib import Path

from xenoform import guardrails as G
from xenoform import transitions_fx as T

ROOT = Path(__file__).resolve().parents[1]


def test_c2_guard_reports_the_overflow_once_per_kind():
    out, msgs = T.guard(["match-cut"] * 53 + ["echo-trail"] * 3)
    assert out.count("match-cut") == 2 and out.count("echo-trail") == 2 and out.count("cut") == 52
    overflow = [m for m in msgs if "already used" in m]
    assert overflow == [
        "match-cut already used 2x; 51 more boundaries are clean beat cuts",
        "echo-trail already used 2x; 1 more boundary is a clean beat cut",
    ]
    # expert keeps every pick and says nothing about the cap
    keep, kept_msgs = T.guard(["match-cut"] * 5, expert=True)
    assert keep == ["match-cut"] * 5 and not [m for m in kept_msgs if "already used" in m]


def _report(rep):
    return rep if isinstance(rep, dict) else rep.as_dict()


def test_c2_the_916_default_resolves_to_native_quietly():
    clean, rep = G.apply({"aspect": "9:16", "vertical_mode": "auto"}, duration=30.0)
    assert clean["vertical_mode"] == "native"
    assert not [m for m in _report(rep)["messages"] if "native_vertical" in m]
    clean, rep = G.apply({"aspect": "9:16"}, duration=30.0)  # unset means auto
    assert clean["vertical_mode"] == "native" and not [m for m in _report(rep)["messages"] if "native_vertical" in m]
    # a crop the user asked for is still clamped, and said
    clean, rep = G.apply({"aspect": "9:16", "vertical_mode": "crop"}, duration=30.0)
    assert clean["vertical_mode"] == "native"
    assert any("native_vertical" in m and "'crop'" in m for m in _report(rep)["messages"])
    # expert keeps auto and is warned, as before
    clean, rep = G.apply({"aspect": "9:16", "vertical_mode": "auto", "expert": True}, duration=30.0)
    assert clean["vertical_mode"] == "auto" and any("native_vertical" in m for m in _report(rep)["messages"])


def test_f2_a_director_animatic_with_a_vibe_cuts_the_stills():
    src = (ROOT / "src" / "xenoform" / "turbo.py").read_text(encoding="utf-8")
    assert 'simple_mode = str(state.get("mode") or "") == "simple" or bool(str(state.get("vibe") or "").strip())' in src
    assert "stills_animatic(directed, state" in src and "def _painted_animatic(" in src
